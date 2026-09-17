"""
Skrip Pengujian Perbandingan Gemini: Stage 1 & Stage 2
=======================================================

Menjalankan analisis Stage 1 (Fundamental Brief) dan Stage 2 (Per-Asset Analysis)
menggunakan dua model Gemini secara bergantian:
  - gemini-3.6-flash     (model flagship terbaru)
  - gemini-3.5-flash-lite (model efisien terbaru)

Data: ASLI dari DB PostgreSQL + MT5 (melalui ToolExecutor yang sudah ada).
Hasil disimpan ke file Markdown terpisah per model di folder scripts/test_results/.

CARA MENJALANKAN:
  cd D:\\ClaudeTrade\\trading-agent
  python ../scripts/test_gemini_comparison.py

CATATAN:
  - Skrip ini menggunakan ToolExecutor asli (DB koneksi nyata).
  - API key diambil dari GEMINI_API_KEYS / GEMINI_API_KEY di .env.
  - submit_fundamental_brief dan submit_asset_analysis AKAN ditulis ke DB.
  - Rotasi API key sesuai logika GeminiClient asli (cooldown + round-robin).
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Path setup — harus dijalankan dari dalam trading-agent/ atau dari root proyek
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
TRADING_AGENT_DIR = SCRIPT_DIR.parent / "trading-agent"
sys.path.insert(0, str(TRADING_AGENT_DIR))

# Load .env
from dotenv import load_dotenv
load_dotenv(TRADING_AGENT_DIR / ".env", override=False)
load_dotenv(TRADING_AGENT_DIR.parent / ".env", override=False)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("GeminiComparison")
# Senyapkan log DB dan HTTP yang ramai
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
OUTPUT_DIR = SCRIPT_DIR / "test_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Model konfigurasi yang akan diuji
# ---------------------------------------------------------------------------
MODELS_TO_TEST = [
    {
        "name": "gemini-3.6-flash",
        "api_model": "gemini-3.6-flash",
        "label": "Gemini 3.6 Flash",
        "thinking_budget": 1024,
        "max_output_tokens": 8192,
    },
    {
        "name": "gemini-3.5-flash-lite",
        "api_model": "gemini-3.5-flash-lite",
        "label": "Gemini 3.5 Flash Lite",
        "thinking_budget": 512,
        "max_output_tokens": 8192,
    },
]

# Simbol Stage 2 — ambil dari settings.yaml (fallback: XAUUSD)
STAGE2_SYMBOL = "XAUUSD"

# COT code untuk XAUUSD
SYMBOL_TO_COT = {
    "XAUUSD": "088691",
    "EURUSD": "099741",
    "GBPUSD": "096742",
    "USDJPY": "097741",
    "AUDUSD": "232741",
    "XTIUSD": "067651",
}

# ---------------------------------------------------------------------------
# Rotasi API Key
# ---------------------------------------------------------------------------

class ApiKeyRotator:
    """Merotasi API key Gemini dengan cooldown handling."""
    _cooldowns: dict[str, float] = {}

    def __init__(self):
        raw_free = os.getenv("GEMINI_API_KEYS", "")
        raw_paid = os.getenv("GEMINI_PAID_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        self.keys = [k.strip() for k in raw_free.split(",") if k.strip()]
        if raw_paid:
            self.keys.append(raw_paid)
            
        self._index = 0
        if not self.keys:
            raise ValueError(
                "Tidak ada GEMINI_API_KEY yang ditemukan.\n"
                "Pastikan GEMINI_API_KEY / GEMINI_API_KEYS / GEMINI_PAID_API_KEY ada di file .env"
            )
        logger.info(f"[ApiKeyRotator] {len(self.keys)} API key(s) ditemukan.")

    def get_key(self) -> Optional[str]:
        now = time.time()
        for _ in range(len(self.keys)):
            key = self.keys[self._index % len(self.keys)]
            self._index += 1
            if self.__class__._cooldowns.get(key, 0) <= now:
                return key
        logger.warning("[ApiKeyRotator] Semua API key sedang dalam cooldown!")
        return None

    def set_cooldown(self, key: str, seconds: float):
        self.__class__._cooldowns[key] = time.time() + seconds
        logger.warning(f"[ApiKeyRotator] Key {key[:8]}... cooldown {seconds:.0f}s.")


# ---------------------------------------------------------------------------
# Klien Gemini ringan (tanpa dependensi DB, hanya HTTP)
# ---------------------------------------------------------------------------

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    """Sanitasi JSON Schema ke format Google OpenAPI."""
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k == "additionalProperties":
            continue
        if k == "type" and isinstance(v, list):
            valid = [t for t in v if t != "null"]
            out[k] = valid[0].upper() if valid else "STRING"
        elif k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif isinstance(v, dict):
            out[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_schema_for_gemini(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


async def gemini_generate(
    rotator: ApiKeyRotator,
    api_model: str,
    system_prompt: str,
    conversation: list[dict],
    tools: list[dict],
    thinking_budget: int = 512,
    max_output_tokens: int = 8192,
    timeout: int = 180,
) -> dict:
    """
    Satu turn panggilan ke Gemini generateContent.

    Returns:
      {
        "text": str | None,
        "tool_calls": [{"name": str, "args": dict, "id": str}],
        "stop_reason": "end_turn" | "tool_use" | "error",
        "input_tokens": int,
        "output_tokens": int,
      }
    """
    import aiohttp

    # Bangun gemini_tools
    gemini_tools = []
    if tools:
        decls = []
        for t in tools:
            if "input_schema" not in t:
                continue
            decls.append({
                "name": t["name"],
                "description": t["description"],
                "parameters": _sanitize_schema_for_gemini(t["input_schema"]),
            })
        if decls:
            gemini_tools = [{"functionDeclarations": decls}]

    # Bangun contents
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": f"System Instructions:\n{system_prompt}"}]})
        contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these instructions carefully."}]})

    tool_id_to_name: dict[str, str] = {}

    for msg in conversation:
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        content = msg["content"]
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for block in content:
                b_type = block.get("type") if isinstance(block, dict) else None
                if b_type == "text":
                    parts.append({"text": block.get("text", "")})
                elif b_type == "tool_result":
                    tid = block.get("tool_use_id", "")
                    tname = tool_id_to_name.get(tid, block.get("_tool_name", "unknown_tool"))
                    raw_content = block.get("content", "")
                    # Truncate very large tool results to avoid context overflow
                    if isinstance(raw_content, str) and len(raw_content) > 8000:
                        raw_content = raw_content[:8000] + "\n... [truncated for context]"
                    parts.append({"text": f"[Result of {tname}]:\n{raw_content}"})
                elif b_type == "tool_use":
                    tname = block.get("name", "")
                    tid = block.get("id", "")
                    if tid:
                        tool_id_to_name[tid] = tname
                    parts.append({"text": f"[Calling tool {tname} with args: {block.get('input', {})}]"})
        if parts:
            contents.append({"role": role, "parts": parts})

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "temperature": 0.1,
        },
    }
    if gemini_tools:
        payload["tools"] = gemini_tools
    if thinking_budget > 0:
        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    url = f"{BASE_URL}/{api_model}:generateContent"

    for attempt in range(5):
        api_key = rotator.get_key()
        if not api_key:
            logger.warning(f"[Gemini] Semua key cooldown. Tunggu 30s... (attempt {attempt+1})")
            await asyncio.sleep(30)
            continue

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    params={"key": api_key},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    body = await resp.text()

                    if resp.status == 429:
                        body_lower = body.lower()
                        if "per_minute" in body_lower or "rpm" in body_lower or "rate" in body_lower:
                            rotator.set_cooldown(api_key, 300)
                        else:
                            rotator.set_cooldown(api_key, 86400)
                        logger.warning(f"[Gemini] 429 on attempt {attempt+1}. Key rotated.")
                        await asyncio.sleep(5 * (attempt + 1))
                        continue

                    if resp.status != 200:
                        logger.warning(f"[Gemini] HTTP {resp.status} on attempt {attempt+1}: {body[:300]}")
                        await asyncio.sleep(10)
                        continue

                    data = json.loads(body)

        except asyncio.TimeoutError:
            logger.warning(f"[Gemini] Timeout ({timeout}s) on attempt {attempt+1}.")
            await asyncio.sleep(10)
            continue
        except Exception as e:
            logger.warning(f"[Gemini] Exception on attempt {attempt+1}: {e}")
            await asyncio.sleep(10)
            continue

        # Parse response
        candidates = data.get("candidates", [])
        if not candidates:
            # Bisa terjadi jika model safety-blocked
            logger.warning(f"[Gemini] Empty candidates on attempt {attempt+1}: {str(data)[:300]}")
            await asyncio.sleep(5)
            continue

        parts = candidates[0].get("content", {}).get("parts", [])
        usage = data.get("usageMetadata", {})

        text_parts = []
        tool_calls = []
        for part in parts:
            if "text" in part and not part.get("thought"):
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                ts = (
                    part.get("thoughtSignature")
                    or part.get("thought_signature")
                    or fc.get("id")
                    or f"gemini_tool_{len(tool_calls)}"
                )
                tool_calls.append({"name": fc["name"], "args": fc.get("args", {}), "id": ts})

        return {
            "text": "\n".join(text_parts) if text_parts else None,
            "tool_calls": tool_calls,
            "stop_reason": "tool_use" if tool_calls else "end_turn",
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
        }

    return {
        "text": None,
        "tool_calls": [],
        "stop_reason": "error",
        "input_tokens": 0,
        "output_tokens": 0,
        "error": "All 5 Gemini API attempts failed.",
    }


# ---------------------------------------------------------------------------
# Agentic loop: Stage 1 atau 2 dengan real ToolExecutor
# ---------------------------------------------------------------------------

async def run_agent_loop(
    rotator: ApiKeyRotator,
    api_model: str,
    model_label: str,
    system_prompt: str,
    initial_user_message: str,
    tools: list[dict],
    stage_name: str,
    db_session,                  # real AsyncSession
    thinking_budget: int = 512,
    max_output_tokens: int = 8192,
    max_turns: int = 25,
) -> dict:
    """
    Menjalankan agentic loop dengan real ToolExecutor (data asli dari DB/MT5).
    """
    from analysis.tool_executor import ToolExecutor

    executor = ToolExecutor(db_session)

    logger.info(f"[{model_label}] Starting {stage_name}...")

    conversation = [{"role": "user", "content": initial_user_message}]
    transcript_entries: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_tool_calls = 0
    turn = 0
    start_time = time.time()

    transcript_entries.append({
        "turn": 0,
        "role": "user",
        "content": initial_user_message,
        "type": "user_message",
    })

    while turn < max_turns:
        turn += 1
        logger.info(f"[{model_label}][{stage_name}] Turn {turn}/{max_turns}...")

        response = await gemini_generate(
            rotator=rotator,
            api_model=api_model,
            system_prompt=system_prompt,
            conversation=conversation,
            tools=tools,
            thinking_budget=thinking_budget,
            max_output_tokens=max_output_tokens,
        )

        if response.get("stop_reason") == "error":
            logger.error(f"[{model_label}][{stage_name}] API error: {response.get('error')}")
            transcript_entries.append({
                "turn": turn,
                "role": "error",
                "content": str(response.get("error")),
                "type": "error",
            })
            break

        total_input_tokens += response["input_tokens"]
        total_output_tokens += response["output_tokens"]

        if response["text"]:
            logger.info(f"[{model_label}][{stage_name}] Turn {turn}: text response ({len(response['text'])} chars).")
            transcript_entries.append({
                "turn": turn,
                "role": "assistant",
                "content": response["text"],
                "type": "text_response",
                "input_tokens": response["input_tokens"],
                "output_tokens": response["output_tokens"],
            })

        if response["tool_calls"]:
            logger.info(f"[{model_label}][{stage_name}] Turn {turn}: {len(response['tool_calls'])} tool call(s).")

        # Tambahkan ke conversation
        assistant_blocks = []
        if response["text"]:
            assistant_blocks.append({"type": "text", "text": response["text"]})
        for tc in response["tool_calls"]:
            assistant_blocks.append({
                "type": "tool_use",
                "name": tc["name"],
                "input": tc["args"],
                "id": tc["id"],
            })
        conversation.append({"role": "assistant", "content": assistant_blocks})

        if response["stop_reason"] == "end_turn" or not response["tool_calls"]:
            logger.info(f"[{model_label}][{stage_name}] Completed at turn {turn}.")
            break

        # Eksekusi tool calls — ASLI dari DB/MT5
        tool_result_blocks = []
        for tc in response["tool_calls"]:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]
            total_tool_calls += 1

            logger.info(f"[{model_label}][{stage_name}]   Tool #{total_tool_calls}: {tool_name}({list(tool_args.keys())})")

            try:
                result = await executor.execute(tool_name, tool_args)
            except Exception as e:
                logger.warning(f"[{model_label}][{stage_name}]   Tool {tool_name} error: {e}")
                result = {"error": str(e), "tool": tool_name}

            result_str = json.dumps(result, ensure_ascii=False, indent=2, default=str)

            transcript_entries.append({
                "turn": turn,
                "role": "tool",
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_result": result,
                "type": "tool_call",
            })

            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "_tool_name": tool_name,
                "content": result_str,
            })

        conversation.append({"role": "user", "content": tool_result_blocks})

    elapsed = time.time() - start_time
    logger.info(
        f"[{model_label}][{stage_name}] Done: {turn} turns, "
        f"{total_tool_calls} tool calls, {total_input_tokens}in/{total_output_tokens}out tokens, "
        f"{elapsed:.1f}s"
    )

    return {
        "transcript": transcript_entries,
        "turns": turn,
        "tool_calls": total_tool_calls,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# System prompts — identik dengan yang digunakan sistem utama
# ---------------------------------------------------------------------------

STAGE1_SYSTEM_PROMPT = """You are an expert macro trading analyst for a proprietary FX and Gold trading system.
Your role is to analyze current fundamental and macro conditions to produce a structured brief
that will guide per-asset trade decisions.

## BUDGET-AWARE WORKFLOW
This system operates on a limited monthly budget. Do not call tools more than necessary.

## Workflow — Execute in this exact order:
1. get_news_digest() — Start with the pre-processed news digest
   → Fallback: get_news_items(hours_back=12) if digest unavailable
2. get_economic_calendar() — Upcoming/recent high-impact events (next 48h, past 24h)
3. get_dxy() — US Dollar Index trend (CRITICAL: master context for all USD pairs)
4. get_treasury_yields() — Yield curve shape and trend (5 days)
5. get_interest_rates() — Current central bank rates
6. get_fedwatch_probabilities() — Market expectations for next Fed move
7. get_vix() — Risk sentiment gauge
8. get_precomputed_cot_signals() — Institutional positioning signals
   → Fallback: get_cot_report() if precomputed unavailable
9. get_surprise_summary() — Aggregated economic surprise scores per currency
10. get_price_momentum(symbol="EURUSD", timeframe="H4", lookback_bars=20) — USD momentum proxy
    IMPORTANT: Do NOT call get_price_momentum with symbol="DXY". Use get_dxy() instead.
    If EURUSD moved DOWN (pct_change negative) = USD strengthening.
    If EURUSD moved UP (pct_change positive) = USD weakening.

## Mandatory Analytical Framework

**[MACRO REGIME]** What is the current macro regime? (Risk-on/Risk-off? Stagflation? Disinflation?)

**[USD THESIS]** What is driving USD? Rate differentials? Safe haven flows? Growth concerns?
Evidence: DXY trend + yields + Fed expectations + surprise data

**[INTER-MARKET]** Cross-validate these signals in this order:
1. DXY trend direction
2. Yields direction — should confirm DXY
3. COT net positioning — institutional bias
4. VIX level — risk environment
5. Economic surprise scores — momentum
If ≥3 of 5 align → HIGH confidence. If only 2 → MEDIUM. If ≤1 → cite contradiction explicitly.

**[BIAS TABLE]** Assign bias for each: USD, EUR, GBP, JPY, AUD, XAU

**[EXPECTATIONS VS REALITY — PRICED-IN ASSESSMENT]**
Apply all 4 methods to assign a Priced-In Score (1-10):
- Method 1: get_fedwatch_probabilities → dominant probability → score
- Method 2: COT net positioning → compare to extremes → score
- Method 3: get_price_momentum for relevant asset → run_up_vs_atr → score
- Method 4: News narrative saturation from get_news_digest → repetition → score
Sum scores → composite Priced-In Score (Fully/Largely/Partially/Not Priced In)

**[KEY RISKS]** State explicitly: "This analysis could be wrong if: [condition]"

**[SELF-CRITIQUE]** What am I most uncertain about? What contradictions exist in the data?

## Key Principles
- A 'neutral' bias is valid — do not force directional views when evidence is mixed
- Lower confidence when: data contradicts itself, major event imminent, VIX > 25
- Higher confidence when: DXY/yields/COT/surprise all point same direction
- Do NOT invent information. Only use data from tools.

## Asset Universe: XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, XTIUSD, BTCUSD

## Expected Output for submit_fundamental_brief:
- macro_narrative: 3-4 detailed paragraphs (macro regime, USD thesis, priced-in, self-critique)
- currency_bias: {"USD": "bullish|bearish|neutral", "EUR": ..., "GBP": ..., "JPY": ..., "AUD": ..., "XAU": ...}
- asset_biases: {"XAUUSD": ..., "EURUSD": ..., "GBPUSD": ..., "USDJPY": ..., "AUDUSD": ..., "XTIUSD": ..., "BTCUSD": ...}
- confidence: 0.0 to 1.0
- priced_in_assessment: {priced_in_score, label, dominant_driver, underpriced, post_event_window}
- key_risks: list of strings

MANDATORY DATA QUALITY RULES:
- If get_vix() returns {error: ...}: DO NOT award VIX_OK confluence point.
- If get_cot_report() returns error: Treat COT as neutral/unknown, DO NOT abort.
- If more than 2 tools return errors → submit with reduced confidence.
"""

STAGE1_USER_MESSAGE = """Please perform a complete fundamental macro analysis for the current market session.

Steps:
1. get_news_digest() — Read Broad Market Sentiment and per-currency segments
2. get_economic_calendar() — Next 48h and past 24h high-impact events
3. get_dxy() — USD Index trend (master context). MUST call this.
4. get_treasury_yields() — Yield curve shape and trend (5 days)
5. get_interest_rates() — Current central bank rates
6. get_fedwatch_probabilities() — Fed meeting expectations
7. get_vix() — Risk sentiment gauge
8. get_precomputed_cot_signals() — Institutional positioning
9. get_surprise_summary() — Economic surprise scores by currency
10. get_price_momentum("EURUSD", "H4", 20) — USD proxy (NOT "DXY")

Submit via submit_fundamental_brief() when complete.
"""


STAGE2_SYSTEM_PROMPT = """You are a professional FX and Gold technical analyst with expertise in Smart Money Concepts (SMC/ICT).
Your task is to analyze {symbol} and produce a structured, high-confidence trading decision.

## STEP 0: MANDATORY MARKET REGIME CHECK
Check D1 ADX before scoring any confluence factors.

| Regime (D1 ADX) | Threshold |
|----------------|-----------|
| ADX > 40 (Strong Trend) | 7/14. Trend-following ONLY. |
| ADX 25-40 (Trend) | 7/14. Prefer setups in trend direction. |
| ADX 15-25 (Weak Trend) | 8/14. Be extra selective. |
| ADX < 15 (Ranging) | 9/14. Only trade from extreme S/R. |

State explicitly: "D1 ADX={value}, regime={label}, threshold adjusted to {n}/14"

## WORKFLOW — Execute in this exact order:
0. get_open_positions() — Check portfolio exposure
   get_risk_state() — Check account drawdown/daily P&L
1. get_market_session() — Current session
2. get_fundamental_brief() — Macro context and currency bias for {symbol}
3. get_dxy() — USD context
4. get_technical_indicators("{symbol}", "D1") — Higher timeframe bias FIRST
5. get_structure_breaks("{symbol}", "D1") — Higher timeframe structure (BOS/ChoCH)
6. get_technical_indicators("{symbol}", "H4") — Entry timeframe
7. get_price_history("{symbol}", "H4", 100) — Recent price action
8. get_atr("{symbol}", "H4") — Volatility baseline for SL sizing
9. get_swing_points("{symbol}", "H4") — Market structure
10. get_structure_breaks("{symbol}", "H4") — Entry timeframe structure
11. get_smc_zones("{symbol}", "H4") — Order Blocks + FVGs + Liquidity Zones + S/R
12. get_cot_report(["{cot_code}"]) — Institutional positioning
13. get_vix() — Risk sentiment

## CONFLUENCE SCORECARD (MANDATORY before calling submit_asset_analysis):

```
CONFLUENCE SCORECARD FOR {symbol}:
[ ] F1_FUNDAMENTAL_BIAS: Macro brief supports direction? YES(+2)/NO(0) = __
[ ] F2_DXY_CONFIRMS: DXY trend confirms? YES(+1)/NO(0) = __
[ ] F3_D1_TREND: D1 trend aligns with H4 entry? YES(+2)/NO(0) = __
[ ] F4_RSI_NEUTRAL: RSI not overbought/oversold? YES(+1)/NO(0) = __
[ ] F5_FVG_PROXIMITY: Entry within 0.5x ATR of unfilled FVG? YES(+2)/NO(0) = __
[ ] F6_ORDER_BLOCK: Unmitigated OB within 0.3x ATR? YES(+2)/NO(0) = __
[ ] F7_OTE_ZONE: Entry between Fib 0.618-0.786? YES(+1)/NO(0) = __
[ ] F8_SR_ZONE: Entry at D1 or H4 S/R zone? YES(+1)/NO(0) = __
[ ] F9_COT_ALIGNED: COT not extreme against direction? YES(+1)/NO(0) = __
[ ] F10_VIX_OK: VIX < 20 (+1); 20-25 (0); >25 (-2) = __

SESSION MODIFIER: NY-London Overlap? +1. Off-peak (21:00-00:00 UTC)? -2.
TOTAL RAW SCORE: __ / 14
FINAL THRESHOLD: __ (7 + adjustments)
DECISION: __ (BUY/SELL if score >= threshold, WAIT if 4-6, AVOID if < 4)
```

## MANDATORY BULL/BEAR STRESS TEST:
Before finalizing BUY or SELL, state:
- BULL SCENARIO: "What is the strongest bear argument? What would invalidate my BUY?"
- BEAR SCENARIO: "What is the strongest bull argument? What would invalidate my SELL?"
Include in rationale under: "[STRESS TEST: bull_risk/bear_risk]"

## DECISION RULES (MANDATORY):
1. D1 vs H4 structure conflict → WAIT or AVOID
2. Macro Bias vs Technical conflict → WAIT or AVOID
3. Cannot reach confluence threshold → WAIT
4. BUY/SELL: SL must be > 1.5x ATR from entry AND beyond structural level
5. TP must achieve R:R >= 1:2
6. If priced_in_score >= 8 AND major event within 12h → DOWNGRADE to WAIT
7. Always state: "Priced-in score: X/10 — [impact on decision]"

Submit via submit_asset_analysis() when complete.
"""

STAGE2_USER_MESSAGE = """Analyze {symbol} for trading opportunities using REAL data from DB/MT5.

Follow the workflow in your system instructions exactly:
0. get_open_positions() then get_risk_state()
1. get_market_session()
2. get_fundamental_brief()
3. get_dxy()
4. get_technical_indicators("{symbol}", "D1")
5. get_structure_breaks("{symbol}", "D1")
6. get_technical_indicators("{symbol}", "H4")
7. get_price_history("{symbol}", "H4", 100)
8. get_atr("{symbol}", "H4")
9. get_swing_points("{symbol}", "H4")
10. get_structure_breaks("{symbol}", "H4")
11. get_smc_zones("{symbol}", "H4")
12. get_cot_report(["{cot_code}"])
13. get_vix()

MANDATORY: Fill out the complete CONFLUENCE SCORECARD before submitting.
MANDATORY: Perform BULL/BEAR STRESS TEST before submitting.
MANDATORY: State "Priced-in score: X/10 — [impact]" in rationale.
MANDATORY: Submit decision via submit_asset_analysis().
"""


# ---------------------------------------------------------------------------
# Tools definitions — identik dengan tools_definitions.py asli
# ---------------------------------------------------------------------------

def _tool(name, description, properties, required):
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties, "required": required},
    }


STAGE1_TOOLS = [
    _tool("get_news_digest", "Get pre-processed news digest organized by currency.", {"hours_back": {"type": "integer"}}, []),
    _tool("get_news_items", "Get raw news items from DB.", {
        "limit": {"type": "integer"}, "hours_back": {"type": "integer"}, "currency_filter": {"type": "string"},
    }, []),
    _tool("get_economic_calendar", "Get upcoming and recent high-impact economic events.", {
        "hours_ahead": {"type": "integer"}, "hours_behind": {"type": "integer"},
        "impact_filter": {"type": "string"}, "currency_filter": {"type": "string"},
    }, []),
    _tool("get_dxy", "Get US Dollar Index data and trend.", {}, []),
    _tool("get_treasury_yields", "Get US Treasury yield data.", {}, []),
    _tool("get_interest_rates", "Get current central bank interest rates.", {}, []),
    _tool("get_fedwatch_probabilities", "Get CME FedWatch rate probabilities.", {}, []),
    _tool("get_vix", "Get VIX volatility index.", {}, []),
    _tool("get_precomputed_cot_signals", "Get pre-computed COT institutional positioning signals.", {}, []),
    _tool("get_cot_report", "Get raw CFTC COT report data.", {
        "market_codes": {"type": "array", "items": {"type": "string"}},
    }, []),
    _tool("get_surprise_summary", "Get economic surprise scores per currency.", {}, []),
    _tool("get_price_momentum", "Get price momentum statistics for a symbol.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
        "lookback_bars": {"type": "integer"},
    }, ["symbol"]),
    _tool("get_fear_greed_index", "Get crypto fear and greed index.", {}, []),
    _tool("get_market_session", "Get current active forex market session.", {}, []),
    _tool("submit_fundamental_brief", "Submit the completed fundamental macro brief to DB.", {
        "macro_narrative": {"type": "string"},
        "currency_bias": {"type": "object"},
        "asset_biases": {"type": "object"},
        "confidence": {"type": "number"},
        "priced_in_assessment": {"type": "object"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
    }, ["macro_narrative", "currency_bias", "confidence"]),
]


STAGE2_TOOLS = [
    _tool("get_open_positions", "Get all currently open trading positions.", {}, []),
    _tool("get_risk_state", "Get current risk state (drawdown, circuit breaker, etc.).", {}, []),
    _tool("get_account_info", "Get trading account balance and margin info.", {}, []),
    _tool("get_market_session", "Get current active forex market session.", {}, []),
    _tool("get_fundamental_brief", "Get the latest fundamental macro brief from Stage 1.", {}, []),
    _tool("get_dxy", "Get US Dollar Index data.", {}, []),
    _tool("get_technical_indicators", "Get technical indicators for a symbol and timeframe.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_structure_breaks", "Get BOS/ChoCH structure breaks.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_price_history", "Get OHLCV price history.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"}, "bars": {"type": "integer"},
    }, ["symbol", "timeframe"]),
    _tool("get_atr", "Get Average True Range for SL sizing.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_swing_points", "Get swing highs/lows for market structure.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_smc_zones", "Get SMC zones: Order Blocks + FVGs + Liquidity + S/R.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_order_blocks", "Get Order Block zones.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_fvg_zones", "Get Fair Value Gap zones.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_liquidity_zones", "Get liquidity zones.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_sr_zones", "Get support/resistance zones.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol", "timeframe"]),
    _tool("get_cot_report", "Get CFTC COT institutional positioning data.", {
        "market_codes": {"type": "array", "items": {"type": "string"}},
    }, []),
    _tool("get_vix", "Get VIX risk sentiment gauge.", {}, []),
    _tool("get_price_momentum", "Get price momentum statistics.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"}, "lookback_bars": {"type": "integer"},
    }, ["symbol"]),
    _tool("get_fibonacci_levels", "Get Fibonacci retracement levels.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
        "swing_high": {"type": "number"}, "swing_low": {"type": "number"},
    }, ["symbol"]),
    _tool("get_precomputed_cot_signals", "Get precomputed COT signals.", {}, []),
    _tool("get_precomputed_indicator_signals", "Get precomputed technical indicator signals.", {
        "symbol": {"type": "string"}, "timeframe": {"type": "string"},
    }, ["symbol"]),
    _tool("get_market_regime", "Get market regime (trending/ranging) based on ADX.", {
        "symbols": {"type": "array", "items": {"type": "string"}}, "timeframe": {"type": "string"},
    }, []),
    _tool("get_recent_activity", "Get recent trading system activity log.", {}, []),
    _tool("get_retail_sentiment", "Get retail trader sentiment.", {
        "symbol": {"type": "string"},
    }, []),
    _tool("get_funding_rate", "Get crypto funding rate.", {
        "symbol": {"type": "string"},
    }, []),
    _tool("submit_asset_analysis", "Submit the completed per-asset trading decision to DB.", {
        "symbol": {"type": "string"},
        "decision": {"type": "string", "enum": ["buy", "sell", "wait", "avoid"]},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
        "confluence_score": {"type": "integer"},
        "confluence_factors": {"type": "array", "items": {"type": "string"}},
        "entry_price": {"type": "number"},
        "stop_loss": {"type": "number"},
        "take_profit": {"type": "number"},
        "entry_condition": {"type": "string"},
        "invalidation": {"type": "string"},
        "reevaluation_trigger": {"type": "string"},
        "priced_in_score": {"type": "integer"},
    }, ["symbol", "decision", "confidence", "rationale"]),
]


# ---------------------------------------------------------------------------
# Render Markdown
# ---------------------------------------------------------------------------

def render_markdown(
    model_config: dict,
    stage1_result: dict,
    stage2_result: dict,
    symbol: str,
    timestamp: str,
) -> str:
    label = model_config["label"]
    api_model = model_config["api_model"]

    lines = []
    lines.append(f"# Laporan Analisis Gemini: {label}")
    lines.append("")
    lines.append(f"**Model API:** `{api_model}`")
    lines.append(f"**Dijalankan pada:** {timestamp}")
    lines.append(f"**Simbol Stage 2:** {symbol}")
    lines.append(f"**Data:** Asli dari DB PostgreSQL + MT5")
    lines.append("")
    lines.append("---")
    lines.append("")

    def _render_stage(stage_name: str, result: dict):
        lines.append(f"## {stage_name}")
        lines.append("")
        lines.append(f"- **Total Turn:** {result['turns']}")
        lines.append(f"- **Total Tool Calls:** {result['tool_calls']}")
        lines.append(f"- **Input Tokens:** {result['input_tokens']:,}")
        lines.append(f"- **Output Tokens:** {result['output_tokens']:,}")
        lines.append(f"- **Total Tokens:** {result['input_tokens'] + result['output_tokens']:,}")
        lines.append(f"- **Durasi:** {result['elapsed_seconds']:.1f} detik")
        lines.append("")
        lines.append(f"### Transcript Lengkap")
        lines.append("")

        for entry in result["transcript"]:
            etype = entry.get("type", "")

            if etype == "user_message":
                lines.append("#### 📤 User Message (Awal)")
                lines.append("")
                lines.append("```")
                lines.append(entry["content"])
                lines.append("```")
                lines.append("")

            elif etype == "text_response":
                lines.append(f"#### 🤖 Model Response — Turn {entry['turn']}")
                lines.append("")
                if entry.get("input_tokens") or entry.get("output_tokens"):
                    lines.append(f"*Tokens: {entry.get('input_tokens', 0):,} in / {entry.get('output_tokens', 0):,} out*")
                    lines.append("")
                lines.append(entry["content"])
                lines.append("")

            elif etype == "tool_call":
                lines.append(f"#### 🔧 Tool Call — Turn {entry['turn']}: `{entry['tool_name']}`")
                lines.append("")
                if entry.get("tool_args"):
                    lines.append("**Args:**")
                    lines.append("```json")
                    lines.append(json.dumps(entry["tool_args"], ensure_ascii=False, indent=2))
                    lines.append("```")
                    lines.append("")
                lines.append("**Result (dari DB/MT5):**")
                lines.append("```json")
                result_str = json.dumps(entry["tool_result"], ensure_ascii=False, indent=2, default=str)
                lines.append(result_str)
                lines.append("```")
                lines.append("")

            elif etype == "error":
                lines.append(f"#### ❌ Error — Turn {entry['turn']}")
                lines.append("")
                lines.append(f"```\n{entry['content']}\n```")
                lines.append("")

        lines.append("---")
        lines.append("")

    _render_stage("Stage 1: Analisis Fundamental Makro", stage1_result)
    _render_stage(f"Stage 2: Analisis Per-Aset ({symbol})", stage2_result)

    # Ringkasan
    lines.append("## Ringkasan Statistik")
    lines.append("")
    lines.append("| Metrik | Stage 1 | Stage 2 |")
    lines.append("|--------|---------|---------|")
    lines.append(f"| Turns | {stage1_result['turns']} | {stage2_result['turns']} |")
    lines.append(f"| Tool Calls | {stage1_result['tool_calls']} | {stage2_result['tool_calls']} |")
    lines.append(f"| Input Tokens | {stage1_result['input_tokens']:,} | {stage2_result['input_tokens']:,} |")
    lines.append(f"| Output Tokens | {stage1_result['output_tokens']:,} | {stage2_result['output_tokens']:,} |")
    lines.append(f"| Total Tokens | {stage1_result['input_tokens'] + stage1_result['output_tokens']:,} | {stage2_result['input_tokens'] + stage2_result['output_tokens']:,} |")
    lines.append(f"| Durasi | {stage1_result['elapsed_seconds']:.1f}s | {stage2_result['elapsed_seconds']:.1f}s |")
    lines.append("")

    grand_total = (
        stage1_result['input_tokens'] + stage1_result['output_tokens'] +
        stage2_result['input_tokens'] + stage2_result['output_tokens']
    )
    grand_time = stage1_result['elapsed_seconds'] + stage2_result['elapsed_seconds']
    lines.append(f"**Grand Total Tokens:** {grand_total:,}")
    lines.append(f"**Grand Total Durasi:** {grand_time:.1f} detik")
    lines.append("")
    lines.append("---")
    lines.append(f"*Laporan dihasilkan oleh `test_gemini_comparison.py` pada {timestamp}*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    from database.db import get_session, close_db

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")
    timestamp_readable = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    logger.info("=" * 70)
    logger.info("  GEMINI COMPARISON TEST: Stage 1 & Stage 2 (DATA ASLI DB/MT5)")
    logger.info(f"  Timestamp: {timestamp_readable}")
    logger.info(f"  Models: {[m['api_model'] for m in MODELS_TO_TEST]}")
    logger.info("=" * 70)

    # Inisialisasi rotator
    try:
        rotator = ApiKeyRotator()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Build prompts untuk simbol yang dipilih
    cot_code = SYMBOL_TO_COT.get(STAGE2_SYMBOL, "N/A")
    stage2_system = STAGE2_SYSTEM_PROMPT.replace("{symbol}", STAGE2_SYMBOL).replace("{cot_code}", cot_code)
    stage2_user = STAGE2_USER_MESSAGE.replace("{symbol}", STAGE2_SYMBOL).replace("{cot_code}", cot_code)

    results_summary = []

    for model_cfg in MODELS_TO_TEST:
        label = model_cfg["label"]
        api_model = model_cfg["api_model"]
        thinking_budget = model_cfg["thinking_budget"]
        max_output_tokens = model_cfg["max_output_tokens"]

        logger.info("")
        logger.info(f"{'='*60}")
        logger.info(f"  Testing: {label} ({api_model})")
        logger.info(f"{'='*60}")

        # ---- STAGE 1 ----
        logger.info(f"[{label}] Running Stage 1 (Fundamental Macro Analysis)...")
        async with get_session() as session1:
            stage1_result = await run_agent_loop(
                rotator=rotator,
                api_model=api_model,
                model_label=label,
                system_prompt=STAGE1_SYSTEM_PROMPT,
                initial_user_message=STAGE1_USER_MESSAGE,
                tools=STAGE1_TOOLS,
                stage_name="Stage1",
                db_session=session1,
                thinking_budget=thinking_budget,
                max_output_tokens=max_output_tokens,
                max_turns=25,
            )

        logger.info(f"[{label}] Stage 1 done. Waiting 5s before Stage 2...")
        await asyncio.sleep(5)

        # ---- STAGE 2 ----
        logger.info(f"[{label}] Running Stage 2 (Per-Asset: {STAGE2_SYMBOL})...")
        async with get_session() as session2:
            stage2_result = await run_agent_loop(
                rotator=rotator,
                api_model=api_model,
                model_label=label,
                system_prompt=stage2_system,
                initial_user_message=stage2_user,
                tools=STAGE2_TOOLS,
                stage_name=f"Stage2_{STAGE2_SYMBOL}",
                db_session=session2,
                thinking_budget=thinking_budget,
                max_output_tokens=max_output_tokens,
                max_turns=25,
            )

        # ---- Simpan ke Markdown ----
        md_content = render_markdown(
            model_config=model_cfg,
            stage1_result=stage1_result,
            stage2_result=stage2_result,
            symbol=STAGE2_SYMBOL,
            timestamp=timestamp_readable,
        )

        safe_model = api_model.replace("-", "_").replace(".", "_")
        output_path = OUTPUT_DIR / f"{timestamp}_{safe_model}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"[{label}] ✅ Results saved → {output_path}")

        results_summary.append({
            "model": label,
            "api_model": api_model,
            "stage1_turns": stage1_result["turns"],
            "stage1_tools": stage1_result["tool_calls"],
            "stage1_tokens": stage1_result["input_tokens"] + stage1_result["output_tokens"],
            "stage1_elapsed": stage1_result["elapsed_seconds"],
            "stage2_turns": stage2_result["turns"],
            "stage2_tools": stage2_result["tool_calls"],
            "stage2_tokens": stage2_result["input_tokens"] + stage2_result["output_tokens"],
            "stage2_elapsed": stage2_result["elapsed_seconds"],
            "output_file": str(output_path),
        })

        if model_cfg != MODELS_TO_TEST[-1]:
            logger.info("Waiting 15s sebelum model berikutnya...")
            await asyncio.sleep(15)

    # Tutup DB
    await close_db()

    # ---- Final summary ----
    logger.info("")
    logger.info("=" * 70)
    logger.info("  PERBANDINGAN SELESAI")
    logger.info("=" * 70)
    logger.info("")
    logger.info(f"{'Model':<28} {'S1 Turn':>8} {'S1 Tools':>9} {'S1 Tok':>9} {'S2 Turn':>8} {'S2 Tools':>9} {'S2 Tok':>9}")
    logger.info("-" * 88)
    for r in results_summary:
        logger.info(
            f"{r['model']:<28} {r['stage1_turns']:>8} {r['stage1_tools']:>9} "
            f"{r['stage1_tokens']:>9,} {r['stage2_turns']:>8} {r['stage2_tools']:>9} {r['stage2_tokens']:>9,}"
        )
    logger.info("")
    logger.info("Output files:")
    for r in results_summary:
        logger.info(f"  {r['model']}: {r['output_file']}")
    logger.info("")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
