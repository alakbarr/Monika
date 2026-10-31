import json
import logging
from typing import Any, Dict, Optional, Union

from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager
from monika.infrastructure.llm.prompt_disciplines import get_universal_execution_discipline
from monika.infrastructure.providers.base_provider import BaseLLMClient

logger = logging.getLogger("TradingAgent.BearAnalyst")


def _clean_json_str(s: Any) -> str:
    if hasattr(s, "text") and isinstance(s.text, str):
        s = s.text
    elif hasattr(s, "content") and isinstance(s.content, str):
        s = s.content
    s = str(s).strip()
    if "```json" in s:
        s = s.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in s:
        s = s.split("```", 1)[1].split("```", 1)[0].strip()
    elif "{" in s and "}" in s:
        start = s.find("{")
        end = s.rfind("}") + 1
        s = s[start:end].strip()
    return s


async def generate_bear_dissent(
    client: BaseLLMClient,
    symbol: str,
    original_context: dict,
    bull_claim: dict,
    fact_sheet: Union[str, Dict[str, Any]],
    rebuttal: Optional[Dict[str, Any]] = None,
) -> dict:
    decision = str(original_context.get("decision", "buy")).lower()
    is_long = decision in ("buy", "long")
    is_conflict = decision in ("conflict_adjudication", "wait", "neutral")

    if is_long:
        role_desc = (
            "You are the Bearish Analyst for the target asset specified in the user message.\n"
            "A BUY (Long) trade has been proposed. Your job is to rigorously challenge the long thesis and 'original_context'.\n"
            "Scrutinize the entry price, SL, and TP. Identify why the Long SL is vulnerable to downside sweeps, "
            "overhead resistance levels that could block the upward TP, and any ignored bearish catalysts in the Fact Sheet.\n"
            "MANDATORY: Inspect dealing range (if price is in premium > 0.50, buying carries poor asymmetry). "
            "Inspect order flow for bearish CVD divergence (distribution into highs) and negative book imbalance."
        )
        score_desc = (
            "RISK SEVERITY ANCHORS (mandatory reference):\n"
            "- 9-10: Fatal flaw! Long SL placed in liquidity grab zone, heavy overhead resistance, or thesis opposes dominant macro/DXY trends.\n"
            "- 6-8: Significant downside risk. Poor R:R or setup trades against elevated VIX / imminent high-impact news event.\n"
            "- 3-5: Standard risk. Minor resistance levels exist en route to TP, but overall bullish trend structure supports the setup.\n"
            "- 1-2: Negligible downside risk. Bullish thesis is clean with strong multi-timeframe confirmation and no obvious resistance."
        )
    elif is_conflict:
        role_desc = (
            "You are the Senior Institutional Bear Advocate for the target asset specified in the user message.\n"
            "Your task: Formulate the highest-conviction SHORT proposal or identify fatal downside risks to the asset.\n"
            "SMC & QUANTITATIVE GROUNDING RULES:\n"
            "1. Dealing Range Location: Short entries are optimal in PREMIUM (> 0.50 of recent dealing range). "
            "Examine local swing high/low in the Fact Sheet to verify premium location.\n"
            "2. Trend Exhaustion & Chasing Guard: Do NOT short at deep discount lows; wait for pullback to unmitigated supply/resistance.\n"
            "3. Structural Trade Levels: Identify proposed_entry, proposed_sl (minimum 1.0x ATR distance above entry), "
            "and proposed_tp (near unmitigated lower liquidity/support). Target minimum R:R >= 1.50.\n"
            "4. Rebuttal of Bull Claims: Directly refute the Bull thesis. Explain why upside rallies will stall at overhead resistance.\n"
            "5. Microstructure: Cite order flow confluences (CVD bearish divergence, negative delta, or ask stacking) if available."
        )
        score_desc = (
            "SHORT THESIS STRENGTH ANCHORS (mandatory reference):\n"
            "- 9-10: Multiple independent bearish confluences align (premium location + overhead resistance + macro headwind), "
            "SL protected by structural resistance >= 1.0x ATR, no meaningful upside counter-evidence in Fact Sheet.\n"
            "- 6-8: Solid bearish setup with premium/SMC resistance, but contains 1 minor caveat (e.g. approaching minor support).\n"
            "- 3-5: Short setup has merit but price sits in discount or material bullish counter-evidence exists.\n"
            "- 1-2: Bearish thesis is completely broken; all indicators, macro, and structure are strongly bullish."
        )
    else:
        role_desc = (
            "You are the Bearish Analyst for the target asset specified in the user message.\n"
            "Your job is to defend the proposed SELL (Short) entry and take profit levels.\n"
            "Focus on identifying downside breakdown catalysts, strong overhead resistance protecting the SL above, "
            "and why the lower TP is conservative or achievable in the current bearish market structure.\n"
            "MANDATORY: Inspect and leverage the 'order_flow' data in the Fact Sheet. Cite aggressive delta selling "
            "(CVD divergence = BEARISH) and negative book imbalance (bid exhaustion / heavy ask presence) as primary structural proof."
        )
        score_desc = (
            "SHORT THESIS STRENGTH ANCHORS (mandatory reference):\n"
            "- 9-10: Multiple independent bearish confluences align (structure + macro + positioning), SL protected by overhead resistance, no meaningful upside counter-evidence in Fact Sheet.\n"
            "- 6-8: Solid bearish setup with macro support, but contains 1 minor caveat (e.g. approaching minor support).\n"
            "- 3-5: Short setup has merit but material bullish counter-evidence exists.\n"
            "- 1-2: Bearish thesis is completely broken; all indicators, macro, and structure are strongly bullish."
        )

    system_prompt = CacheBreakpointManager.get_canonical_debate_system_prompt()

    schema = {
        "type": "object",
        "properties": {
            "bear_dissent": {"type": "string"},
            "risk_severity": {"type": "integer", "minimum": 1, "maximum": 10},
            "evidence_cited": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string"},
                "description": "MANDATORY: List of exact numerical data points from the Fact Sheet that support your thesis. Example: ['ATR_14(H4)=2.45', 'DXY_trend=strengthening +0.4%', 'VIX=28.5', 'CVD_divergence=BEARISH', 'Book_imbalance=-0.45']. Minimum 2 items.",
            },
            "key_levels": {
                "type": "array",
                "items": {"type": "number"},
                "description": "List of key price levels cited in thesis (e.g. resistance, supply zone, FVG, swing pivot, order block boundary).",
            },
            "falsification_triggers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete price or macro conditions that would immediately invalidate the bearish argument.",
            },
            "proposed_entry": {"type": "number", "description": "Proposed Short entry price."},
            "proposed_sl": {
                "type": "number",
                "description": "Proposed Stop Loss above structural resistance (>= 1.0x ATR distance).",
            },
            "proposed_tp": {"type": "number", "description": "Proposed Take Profit near unmitigated lower liquidity."},
            "rr_ratio": {
                "type": "number",
                "description": "Risk to reward ratio (|entry - tp| / |sl - entry|). Target >= 1.5.",
            },
            "bull_rebuttal": {"type": "string", "description": "Direct refutation of opposing bullish claims."},
        },
        "required": ["bear_dissent", "risk_severity", "evidence_cited"],
    }

    task_directive = (
        f"[TARGET ASSET]: {symbol} | [DIRECTION]: {decision.upper()}\n"
        f"{role_desc}\n\n"
        f"{score_desc}\n\n"
        "Generate bear analysis based strictly on the setup and Fact Sheet above. "
        "Return valid JSON strictly matching the schema."
    )
    append_ledger: Dict[str, Any] = {
        "bull_claim": bull_claim,
    }
    if rebuttal:
        append_ledger["bull_rebuttal"] = rebuttal
    base_user_msg = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fact_sheet,
        original_context=original_context,
        append_ledger=append_ledger,
        task_directive=task_directive,
    )

    temp = getattr(client, "default_temperature", 0.2)
    last_err = None
    for attempt in range(2):
        try:
            user_msg = (
                base_user_msg
                if attempt == 0
                else f"{base_user_msg}\n\nYour previous response was not valid JSON ({last_err}). Return ONLY valid JSON matching the schema."
            )
            raw_tok = getattr(client, "max_tokens", None)
            call_max_tokens = max(int(raw_tok), 8192) if isinstance(raw_tok, (int, float)) else 8192
            resp = await client.generate_content(
                system_prompt=system_prompt,
                user_message=user_msg,
                temperature=temp,
                response_schema=schema,
                max_tokens=call_max_tokens,
            )
            if not resp:
                raise ValueError("Empty response from LLM")
            return json.loads(_clean_json_str(resp))
        except Exception as e:
            last_err = e
            logger.warning(f"Bear Analyst parse attempt {attempt + 1}/2 failed: {e}")

    logger.error(f"Failed to parse Bear Analyst JSON after 2 attempts: {last_err}")
    return {
        "bear_dissent": f"Fallback: Bearish counter-thesis evaluation incomplete ({last_err}); evaluating standard structural risk.",
        "risk_severity": 5,
        "evidence_cited": ["Standard structural risk parameters"],
        "parse_error": True,
        "degraded_fallback": True,
    }


# Canonical alias for debate lifecycle
generate_bear_claim = generate_bear_dissent


async def generate_bear_rebuttal(
    client: BaseLLMClient,
    symbol: str,
    original_context: dict,
    fact_sheet: Union[str, Dict[str, Any]],
    bear_claim: dict,
    bull_dissent: dict,
) -> dict:
    """Round 2 rebuttal generated by Bear Analyst to defend a proposed SELL setup against Bullish dissent."""
    role_desc = (
        f"You are the Bearish Analyst for {symbol}.\n"
        f"The Bullish Analyst has issued a counter-argument/dissent challenging your proposed SELL (Short) setup.\n"
        f"Your task is to provide a grounded, rigorous Round 2 dialectic rebuttal defending the Short thesis.\n"
        f"Directly confront the specific criticisms in 'bull_dissent'. Cite precise numerical confluences from the Fact Sheet "
        f"(including 'order_flow' CVD divergence and order book imbalance) to demonstrate why the short trade remains viable, "
        f"or concede specific structural risks if the Bull's points are insurmountable."
    )
    score_desc = (
        "REBUTTAL STRENGTH ANCHORS (mandatory reference):\n"
        "- 9-10: Complete refutation! Bull's arguments rely on false assumptions or out-of-context data; verified HTF resistance/catalysts completely nullify the bull threat.\n"
        "- 6-8: Effective mitigation. Bull raises valid risk, but entry/SL buffers or secondary indicators adequately cover the concern.\n"
        "- 3-5: Weak rebuttal. Bull's critique exposes genuine vulnerability; Bear can only offer partial or rhetorical defense.\n"
        "- 1-2: Capitulation. Bull's critique identifies a fatal flaw in the short setup that cannot be defended."
    )

    system_prompt = CacheBreakpointManager.get_canonical_debate_system_prompt()

    schema = {
        "type": "object",
        "properties": {
            "rebuttal_thesis": {"type": "string"},
            "rebuttal_strength": {"type": "integer", "minimum": 1, "maximum": 10},
            "rebuttal_evidence": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string"},
                "description": "MANDATORY: List of exact numerical data points from the Fact Sheet refuting bull points. Minimum 2 items.",
            },
            "conceded_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of valid points conceded to the Bull Analyst, if any.",
            },
        },
        "required": ["rebuttal_thesis", "rebuttal_strength", "rebuttal_evidence"],
    }

    task_directive = (
        f"[TARGET ASSET]: {symbol} | [DIRECTION]: SELL\n"
        f"{role_desc}\n\n"
        f"{score_desc}\n\n"
        "Provide Round 2 Bearish Rebuttal confronting the Bull Dissent based strictly on the Fact Sheet. "
        "Return valid JSON strictly matching the schema."
    )
    append_ledger = {
        "bear_claim": bear_claim,
        "bull_dissent": bull_dissent,
    }
    base_user_msg = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fact_sheet,
        original_context=original_context,
        append_ledger=append_ledger,
        task_directive=task_directive,
    )
    temp = getattr(client, "default_temperature", 0.2)
    last_err = None
    for attempt in range(2):
        try:
            user_msg = (
                base_user_msg
                if attempt == 0
                else f"{base_user_msg}\n\nYour previous response was not valid JSON ({last_err}). Return ONLY valid JSON matching the schema."
            )
            raw_tok = getattr(client, "max_tokens", None)
            call_max_tokens = max(int(raw_tok), 8192) if isinstance(raw_tok, (int, float)) else 8192
            resp = await client.generate_content(
                system_prompt=system_prompt,
                user_message=user_msg,
                temperature=temp,
                response_schema=schema,
                max_tokens=call_max_tokens,
            )
            if not resp:
                raise ValueError("Empty response from LLM")
            return json.loads(_clean_json_str(resp))
        except Exception as e:
            last_err = e
            logger.warning(f"Bear Analyst rebuttal parse attempt {attempt + 1}/2 failed: {e}")

    logger.error(f"Failed to parse Bear Analyst Rebuttal JSON after 2 attempts: {last_err}")
    return {
        "rebuttal_thesis": f"Failed to generate rebuttal due to parse error: {last_err}",
        "rebuttal_strength": 0,
        "rebuttal_evidence": [],
        "conceded_points": [],
        "parse_error": True,
        "degraded_fallback": True,
    }


# Canonical alias for debate lifecycle
generate_bear_claim = generate_bear_dissent
