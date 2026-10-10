"""
Benchmark Runner for Dialectical Debate across 6 LLMs via OpenRouter.
Completely isolated in-memory execution.
Zero database modification, zero live broker order execution.
Produces full transparent input/output/thinking Markdown report.
Evaluates:
  1. Council Self-Debate (EURUSD): Bull Advocacy -> Bear Dissent -> Investment Judge Ruling
  2. Standardized Fatal Flaw Stress Test (USDJPY): Investment Judge Capital Preservation Defense
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Set up paths
REPO_ROOT = Path(r"D:\Monika")
sys.path.insert(0, str(REPO_ROOT / "trading-agent"))
os.chdir(str(REPO_ROOT))

# Ensure stdout handles UTF-8 on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.settings import load_all_config
from analysis.providers.openrouter_provider import OpenRouterProvider
from utils.api.openrouter_rate_limiter import get_paid_key
from utils.analytics.pricing import cost_usd
from analysis.debate.bull_analyst import generate_bull_advocacy
from analysis.debate.bear_analyst import generate_bear_dissent
from analysis.debate.investment_judge import evaluate_debate
from analysis.debate.exact_decimal_math import to_exact_decimal, exact_rr_ratio

# Evaluated models (Claude Opus 5.5 and Grok 4.6 explicitly excluded)
MODELS_TO_BENCHMARK = [
    {
        "name": "gpt-6.1-sol",
        "display_name": "GPT-6.1 Sol (high)",
        "model_id": "openai/gpt-6.1-sol",
        "thinking_level": "high",
        "max_tokens": 16384,
    },
    {
        "name": "muse-spark-1.3",
        "display_name": "Muse Spark 1.3 (xhigh)",
        "model_id": "meta/muse-spark-1.3",
        "thinking_level": "xhigh",
        "max_tokens": 24576,
    },
    {
        "name": "mimo-v2.6-pro",
        "display_name": "MiMo v2.6 Pro (max)",
        "model_id": "xiaomi/mimo-v2.6-pro",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "deepseek-v4-pro",
        "display_name": "DeepSeek v4 Pro (max)",
        "model_id": "deepseek/deepseek-v4-pro",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "kimi-k3",
        "display_name": "Kimi k3 (max)",
        "model_id": "moonshotai/kimi-k3",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "gemini-3.8-flash",
        "display_name": "Gemini 3.8 Flash (high)",
        "model_id": "google/gemini-3.8-flash",
        "thinking_level": "high",
        "max_tokens": 16384,
    },
    {
        "name": "deepseek-v4.1-flash",
        "display_name": "DeepSeek v4.1 Flash (max)",
        "model_id": "deepseek/deepseek-v4.1-flash",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "glm-5.3",
        "display_name": "GLM-5.3 (max)",
        "model_id": "z-ai/glm-5.3",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
    {
        "name": "glm-5.3-flash",
        "display_name": "GLM-5.3 Flash (max)",
        "model_id": "z-ai/glm-5.3-flash",
        "thinking_level": "max",
        "max_tokens": 32768,
    },
]

JSON_OUTPUT_PATH = REPO_ROOT / "trading-agent" / "benchmark" / "results" / "benchmark_debate_results.json"
MARKDOWN_OUTPUT_PATH = REPO_ROOT / "trading-agent" / "benchmark" / "results" / "benchmark_debate_openrouter.md"


class BenchmarkingDebateClient(OpenRouterProvider):
    """
    Subclass that intercepts calls to track exact tokens, thinking tokens,
    and costs in memory without database writes.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_history: List[Dict[str, Any]] = []

    async def _save_token_usage(
        self,
        model_name: str,
        task_name: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        cache_creation_tokens: int = 0,
        thinking_tokens: int = 0,
        exact_cost: Optional[float] = None,
        **kwargs: Any
    ) -> None:
        if exact_cost is not None and isinstance(exact_cost, (int, float)) and exact_cost >= 0:
            calc_cost = round(float(exact_cost), 6)
        else:
            calc_cost = cost_usd(
                model_name,
                input_tokens,
                output_tokens,
                cached_tokens=cached_tokens,
                provider="openrouter"
            )

        self.call_history.append({
            "task_name": task_name,
            "model_name": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "thinking_tokens": thinking_tokens,
            "cost_usd": calc_cost,
            "timestamp": time.time(),
        })


def get_eurusd_debate_data() -> tuple[dict, dict]:
    """Golden production-grade context and fact sheet for EURUSD dialectical debate."""
    ctx = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "rationale": "H1 Bullish Displacement with Order Block mitigation at 1.1350 and FVG fill.",
        "confluence_score": 11,
        "confluence_factors": ["BOS_BULLISH", "FVG_REBALANCE", "LONDON_SESSION_MOMENTUM"],
        "entry_price": 1.1377,
        "stop_loss": 1.1340,
        "take_profit": 1.1460,
        "invalidation": "Break below swing low 1.1342",
        "market_regime": "trending",
        "vix": 17.2,
        "bull_brier_score": 0.18,
        "bear_brier_score": 0.24,
    }

    fs = {
        "symbol": "EURUSD",
        "current_price": 1.1377,
        "atr_14_h4": 0.0045,
        "h4_structure": "BULLISH",
        "m15_structure": "BULLISH",
        "key_support": 1.1340,
        "key_resistance": 1.1460,
        "macro_bias": "Transatlantic divergence and Hormuz oil shock dictate directional positioning.",
        "order_flow": {
            "cvd_divergence": "BULLISH",
            "cvd_delta": "+1,420 contracts (H1)",
            "book_imbalance": 0.35,
            "bid_depth_usd": 14500000,
            "ask_depth_usd": 9400000,
            "institutional_absorption": "Active bid absorption at 1.1355 liquidity pool"
        },
        "dxy_trend": "weakening -0.35%",
        "vix": 17.2,
        "market_regime": "trending",
        "specialist_reliability": {
            "technical": {"trust_weight": 0.92, "chronically_unreliable": False},
            "macro": {"trust_weight": 0.88, "chronically_unreliable": False},
            "sentiment": {"trust_weight": 0.75, "chronically_unreliable": False}
        }
    }
    return ctx, fs


def get_fatal_flaw_trap_data() -> tuple[dict, dict, dict]:
    """Standardized Fatal Flaw Stress Test on USDJPY."""
    trap_ctx = {
        "symbol": "USDJPY",
        "decision": "BUY",
        "rationale": "Momentum continuation following minor H1 break.",
        "confluence_score": 7,
        "confluence_factors": ["H1_MOMENTUM_BREAK"],
        "entry_price": 158.80,
        "stop_loss": 158.45,
        "take_profit": 159.80,
        "invalidation": "Break below 158.40",
        "market_regime": "volatile",
        "vix": 28.5,
        "bull_brier_score": 0.29,
        "bear_brier_score": 0.15,
    }

    golden_bull = {
        "bull_thesis": "H1 breakout above 158.70 with strong upward momentum. Take profit at 159.80 is easily reachable as retail continues chasing the breakout.",
        "strength_score": 7,
        "evidence_cited": ["H1_momentum=strong", "Retail_sentiment=bullish"],
        "key_levels": [158.70, 159.80],
        "falsification_triggers": ["Break below 158.40"]
    }

    golden_bear = {
        "bear_dissent": "FATAL FLAW: The proposed BUY enters directly into an unmitigated D1 bearish supply block at 158.90 with extreme institutional distribution. CVD divergence is severely BEARISH (-0.48) with massive sell absorption. The Stop Loss at 158.45 is located directly within a major sell-side liquidity pool with zero demand structure underneath. Furthermore, the Bank of Japan just announced an emergency policy review causing macro risk-off with VIX surging to 28.5.",
        "risk_severity": 9,
        "evidence_cited": [
            "CVD_divergence=BEARISH (-0.48)",
            "VIX=28.5 (volatile regime)",
            "Book_imbalance=-0.52 (heavy ask iceberg selling)",
            "SL_in_liquidity_void=158.45",
            "D1_supply_block=158.90-159.20"
        ],
        "key_levels": [158.90, 158.45, 157.80],
        "falsification_triggers": ["D1 close above 159.50"]
    }

    return trap_ctx, golden_bull, golden_bear


def build_markdown_report(benchmark_record: Dict[str, Any]) -> str:
    """Generate comprehensive, transparent Markdown report for Dialectical Debate benchmark."""
    md = []
    meta = benchmark_record.get("metadata", {})
    results = benchmark_record.get("results", [])

    md.append("# 🏛️ Monika Benchmark: Dialectical Debate & Multi-Agent Deliberation Suite")
    md.append(f"\n> **Execution Date**: `{meta.get('timestamp')}` | **Environment**: OpenRouter Production | **Subsystem**: `analysis/debate`\n")
    md.append("Dokumen ini menyajikan hasil benchmark mendalam evaluasi multi-agent **Dialectical Debate** (Bull Analyst, Bear Analyst, dan Investment Judge) di platform kuantitatif Monika.")
    md.append("Menguji 6 model frontier/open-weights terdepan dalam merumuskan advokasi bullish berbasis bukti kuantitatif (order flow CVD, book imbalance, ATR), menyerang kerentanan risiko (downside sweeps, resistance, liquidity grabs), serta mengadili konsensus investasi dan menegakkan proteksi modal absolut.\n")

    # Table 1: Council Deliberation Scorecard
    md.append("## 1. 📊 Executive Scorecard: Council Deliberation (EURUSD)")
    md.append("| Model | Latency (Total) | Total Tokens | Cost (USD) | Bull Score | Bear Risk | Judge Ruling | Risk Mult | Adjustments |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    for r in results:
        disp = r.get("display_name", r.get("name"))
        lat = f"{r.get('council_total_latency_s', 0.0):.2f}s"
        toks = f"{r.get('council_total_tokens', 0):,}"
        cost = f"${r.get('council_total_cost_usd', 0.0):.6f}"
        b_sc = r.get("bull", {}).get("strength_score", "-")
        br_sc = r.get("bear", {}).get("risk_severity", "-")
        j_dec = (r.get("judge", {}).get("final_decision") or "N/A").upper()
        j_mul = f"{r.get('judge', {}).get('risk_multiplier', 0.0):.2f}x"
        
        # Check adjustments
        adj = []
        if r.get("judge", {}).get("adjusted_entry") is not None:
            adj.append(f"Entry:{r['judge']['adjusted_entry']}")
        if r.get("judge", {}).get("adjusted_sl") is not None:
            adj.append(f"SL:{r['judge']['adjusted_sl']}")
        if r.get("judge", {}).get("adjusted_tp") is not None:
            adj.append(f"TP:{r['judge']['adjusted_tp']}")
        adj_str = ", ".join(adj) if adj else "None"

        md.append(f"| **{disp}** | {lat} | {toks} | {cost} | {b_sc}/10 | {br_sc}/10 | `{j_dec}` | `{j_mul}` | {adj_str} |")

    # Table 2: Fatal Flaw Stress Test Scorecard
    md.append("\n## 2. 🛡️ Capital Preservation Stress Test: Fatal Flaw Trap (USDJPY)")
    md.append("> **Scenario**: Bear Analyst membuktikan FATAL FLAW (`risk_severity = 9`) dengan order block bear, CVD negatif (-0.48), dan regime volatil (VIX=28.5).")
    md.append("> **Monika Directives Mandate**: Investment Judge WAJIB menolak trade (`final_decision = 'avoid'`, `risk_multiplier = 0.0`).\n")
    md.append("| Model | Latency | Judge Verdict | Risk Mult | Native Avoid | Fortress Override | Defense Status |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    for r in results:
        disp = r.get("display_name", r.get("name"))
        trap = r.get("fatal_flaw_trap", {})
        lat = f"{trap.get('latency_s', 0.0):.2f}s"
        dec = (trap.get("final_decision") or "N/A").upper()
        mul = f"{trap.get('risk_multiplier', 0.0):.2f}x"
        native = "✅ YES" if trap.get("native_avoid") else "❌ NO"
        override = "⚠️ YES (Triggered)" if trap.get("fortress_override_triggered") else "None"
        status = "🛡️ PASSED (Fortress Safe)" if trap.get("defense_passed") else "🚨 FAILED (Capital Risk)"
        md.append(f"| **{disp}** | {lat} | `{dec}` | `{mul}` | {native} | {override} | {status} |")

    # Detailed Model Breakdown
    md.append("\n## 3. 🔍 Granular Trajectory & Reasoning Breakdown per Model\n")

    for idx, r in enumerate(results, 1):
        disp = r.get("display_name", r.get("name"))
        mid = r.get("model_id")
        thk = r.get("thinking_level")
        md.append(f"### 3.{idx}. Model: {disp} (`{mid}`)\n")
        md.append(f"- **Thinking Effort / Level**: `{thk}`")
        md.append(f"- **Total Benchmark Latency**: `{r.get('total_latency_s', 0.0):.2f}s` | **Total Cost**: `${r.get('total_cost_usd', 0.0):.6f} USD`")
        md.append(f"- **Total Token Consumption**: `{r.get('total_input_tokens', 0):,}` In | `{r.get('total_output_tokens', 0):,}` Out | `{r.get('total_thinking_tokens', 0):,}` Thinking\n")

        # Bull
        bull = r.get("bull", {})
        md.append("#### 🐂 Phase 1: Bull Advocacy (Long Defense)")
        md.append(f"- **Strength Score**: `{bull.get('strength_score', 'N/A')}/10` | **Latency**: `{bull.get('latency_s', 0.0):.2f}s`")
        md.append(f"- **Evidence Cited**: `{', '.join(bull.get('evidence_cited', []))}`")
        if bull.get("key_levels"):
            md.append(f"- **Key Levels Identified**: `{bull.get('key_levels')}`")
        if bull.get("falsification_triggers"):
            md.append(f"- **Falsification Triggers**: `{bull.get('falsification_triggers')}`")
        md.append(f"\n> **Bull Thesis**:\n> {bull.get('bull_thesis', 'N/A')}\n")

        # Bear
        bear = r.get("bear", {})
        md.append("#### 🐻 Phase 2: Bear Dissent (Downside Risk Challenge)")
        md.append(f"- **Risk Severity Score**: `{bear.get('risk_severity', 'N/A')}/10` | **Latency**: `{bear.get('latency_s', 0.0):.2f}s`")
        md.append(f"- **Evidence Cited**: `{', '.join(bear.get('evidence_cited', []))}`")
        if bear.get("key_levels"):
            md.append(f"- **Key Levels Identified**: `{bear.get('key_levels')}`")
        if bear.get("falsification_triggers"):
            md.append(f"- **Falsification Triggers**: `{bear.get('falsification_triggers')}`")
        md.append(f"\n> **Bear Dissent**:\n> {bear.get('bear_dissent', bear.get('bear_thesis', 'N/A'))}\n")

        # Judge
        judge = r.get("judge", {})
        md.append("#### ⚖️ Phase 3: Investment Judge Adjudication (Council Ruling)")
        md.append(f"- **Final Decision**: `{str(judge.get('final_decision', 'N/A')).upper()}` | **Risk Multiplier**: `{judge.get('risk_multiplier', 0.0):.2f}x` | **Latency**: `{judge.get('latency_s', 0.0):.2f}s`")
        if judge.get("adjusted_entry") or judge.get("adjusted_sl") or judge.get("adjusted_tp"):
            md.append(f"- **Level Adjustments**: Entry=`{judge.get('adjusted_entry')}`, SL=`{judge.get('adjusted_sl')}`, TP=`{judge.get('adjusted_tp')}`")
        md.append(f"\n> **Judge Rationale**:\n> {judge.get('reason', 'N/A')}\n")

        # Fatal Flaw Trap
        trap = r.get("fatal_flaw_trap", {})
        md.append("#### 🛡️ Phase 4: Standardized Fatal Flaw Stress Test (USDJPY)")
        md.append(f"- **Verdict**: `{str(trap.get('final_decision', 'N/A')).upper()}` | **Risk Multiplier**: `{trap.get('risk_multiplier', 0.0):.2f}x`")
        md.append(f"- **Capital Protection Result**: `{ 'PASS (Safe)' if trap.get('defense_passed') else 'FAIL (Vulnerable)' }` (Native Avoid: `{trap.get('native_avoid')}`)")
        md.append(f"\n> **Judge Rationale on Fatal Flaw**:\n> {trap.get('reason', 'N/A')}\n")

        md.append("---\n")

    # Section 4: Architectural Synthesis
    md.append("## 4. 🧠 Comparative Analysis & Architectural Conclusions\n")
    md.append("### 4.1. Dialectical Rigor & Order Flow Integration")
    md.append("- Bull & Bear personas menuntut pemanfaatan bukti mikrostruktural *order flow* (CVD divergence dan book imbalance). Model yang unggul mampu mengintegrasikan metrik kuantitatif eksak dari Fact Sheet tanpa retorika kosong.")
    md.append("\n### 4.2. Bayesian Calibration & Prinsip Mechanical Fortress")
    md.append("- Investment Judge bertindak sebagai benteng pertahanan modal. Sesuai prinsip *'AI Proposes, Mechanical Fortress Disposes'*, proposal dengan risiko fatal (severity >= 9) atau regime volatil wajib ditolak.")
    md.append("- Model yang secara native menolak trade trap membuktikan kehandalan penalaran risiko frontier tanpa memerlukan intervensi override.")

    return "\n".join(md)


async def run_debate_benchmark_for_model(
    model_cfg: Dict[str, Any],
    paid_key: str,
    settings: dict,
    eurusd_ctx: dict,
    eurusd_fs: dict,
    trap_ctx: dict,
    trap_bull: dict,
    trap_bear: dict,
) -> Dict[str, Any]:
    """Execute the full debate suite for a single model."""
    name = model_cfg["name"]
    disp = model_cfg["display_name"]
    model_id = model_cfg["model_id"]
    thinking_level = model_cfg["thinking_level"]
    max_tokens = model_cfg["max_tokens"]

    client = BenchmarkingDebateClient(
        model=model_id,
        api_key=paid_key,
        settings=settings,
        thinking_level=thinking_level,
        max_tokens=max_tokens,
    )

    result_data = {
        "name": name,
        "display_name": disp,
        "model_id": model_id,
        "thinking_level": thinking_level,
        "max_tokens": max_tokens,
        "success": False,
        "bull": {},
        "bear": {},
        "judge": {},
        "fatal_flaw_trap": {},
        "call_records": [],
    }

    t0_all = time.monotonic()

    # -------------------------------------------------------------
    # 1. Council Debate: Bull Analyst (EURUSD)
    # -------------------------------------------------------------
    print(f"      [1/4] Running Bull Analyst for {name}...")
    t0_bull = time.monotonic()
    bull_res = await generate_bull_advocacy(client, "EURUSD", eurusd_ctx, eurusd_fs)
    lat_bull = time.monotonic() - t0_bull
    bull_res["latency_s"] = lat_bull
    result_data["bull"] = bull_res
    print(f"            Bull Score: {bull_res.get('strength_score')}/10 ({lat_bull:.2f}s)")

    await asyncio.sleep(1.0)

    # -------------------------------------------------------------
    # 2. Council Debate: Bear Analyst (EURUSD)
    # -------------------------------------------------------------
    print(f"      [2/4] Running Bear Analyst for {name}...")
    t0_bear = time.monotonic()
    bear_res = await generate_bear_dissent(client, "EURUSD", eurusd_ctx, bull_res, eurusd_fs)
    lat_bear = time.monotonic() - t0_bear
    bear_res["latency_s"] = lat_bear
    result_data["bear"] = bear_res
    print(f"            Bear Risk: {bear_res.get('risk_severity')}/10 ({lat_bear:.2f}s)")

    await asyncio.sleep(1.0)

    # -------------------------------------------------------------
    # 3. Council Debate: Investment Judge (EURUSD)
    # -------------------------------------------------------------
    print(f"      [3/4] Running Investment Judge (Council) for {name}...")
    t0_judge = time.monotonic()
    judge_res = await evaluate_debate(client, "EURUSD", eurusd_ctx, bull_res, bear_res)
    lat_judge = time.monotonic() - t0_judge
    judge_res["latency_s"] = lat_judge
    result_data["judge"] = judge_res
    print(f"            Judge Verdict: {judge_res.get('final_decision')} (Multiplier: {judge_res.get('risk_multiplier')}x, {lat_judge:.2f}s)")

    await asyncio.sleep(1.0)

    # -------------------------------------------------------------
    # 4. Standardized Fatal Flaw Stress Test (USDJPY)
    # -------------------------------------------------------------
    print(f"      [4/4] Running Fatal Flaw Stress Test (USDJPY) for {name}...")
    t0_trap = time.monotonic()
    trap_res = await evaluate_debate(client, "USDJPY", trap_ctx, trap_bull, trap_bear)
    lat_trap = time.monotonic() - t0_trap
    trap_res["latency_s"] = lat_trap

    # Evaluate capital defense compliance
    raw_dec = str(trap_res.get("final_decision", "")).lower()
    raw_mul = float(trap_res.get("risk_multiplier", 1.0) or 0.0)
    has_override = "[FATAL FLAW OVERRIDE]" in str(trap_res.get("rationale", ""))
    is_avoid = (raw_dec == "avoid" and raw_mul == 0.0)
    native_avoid = is_avoid and not has_override

    trap_res["native_avoid"] = native_avoid
    trap_res["fortress_override_triggered"] = has_override
    trap_res["defense_passed"] = is_avoid

    result_data["fatal_flaw_trap"] = trap_res
    print(f"            Trap Defense: {'PASSED' if is_avoid else 'FAILED'} (Native Avoid: {native_avoid}, {lat_trap:.2f}s)")

    # Aggregate records
    t_total = time.monotonic() - t0_all
    result_data["total_latency_s"] = t_total
    result_data["call_records"] = client.call_history

    # Token and cost calculations
    council_records = client.call_history[:3]
    trap_records = client.call_history[3:]

    result_data["council_total_tokens"] = sum(c.get("input_tokens", 0) + c.get("output_tokens", 0) for c in council_records)
    result_data["council_total_cost_usd"] = sum(c.get("cost_usd", 0.0) for c in council_records)
    result_data["council_total_latency_s"] = lat_bull + lat_bear + lat_judge

    result_data["total_input_tokens"] = sum(c.get("input_tokens", 0) for c in client.call_history)
    result_data["total_output_tokens"] = sum(c.get("output_tokens", 0) for c in client.call_history)
    result_data["total_thinking_tokens"] = sum(c.get("thinking_tokens", 0) for c in client.call_history)
    result_data["total_cached_tokens"] = sum(c.get("cached_tokens", 0) for c in client.call_history)
    result_data["total_cost_usd"] = sum(c.get("cost_usd", 0.0) for c in client.call_history)
    result_data["success"] = True

    return result_data


async def main():
    print("=" * 75)
    print("[*] MONIKA BENCHMARK: Dialectical Debate Suite across 6 LLMs via OpenRouter")
    print("=" * 75)

    settings = load_all_config()
    settings["_benchmark_mode"] = True
    settings["_use_fixtures"] = True
    settings["llm"]["providers"]["openrouter"]["enabled"] = True

    paid_key = get_paid_key()
    if not paid_key:
        print("[!] ERROR: No OpenRouter paid key available in configuration or environment.")
        return

    eurusd_ctx, eurusd_fs = get_eurusd_debate_data()
    trap_ctx, trap_bull, trap_bear = get_fatal_flaw_trap_data()

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default=None, help="Specific model to run")
    parser.add_argument("--force", action="store_true", help="Force re-run even if model already exists")
    args = parser.parse_args()

    benchmark_record = {
        "metadata": {
            "suite": "dialectical_debate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runner": "scripts/benchmark_debate_openrouter.py",
        },
        "results": [],
    }

    if JSON_OUTPUT_PATH.exists():
        try:
            with open(JSON_OUTPUT_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "results" in saved:
                    benchmark_record = saved
                    print(f"[*] Loaded {len(benchmark_record['results'])} existing results from {JSON_OUTPUT_PATH.name}")
        except Exception as e:
            print(f"[Warning] Could not load existing benchmark results: {e}")

    targets_to_run = [
        m for m in MODELS_TO_BENCHMARK
        if not args.model or args.model.lower() in m["name"].lower() or args.model.lower() in m["model_id"].lower()
    ]

    total_models = len(targets_to_run)
    for i, target in enumerate(targets_to_run, 1):
        name = target["name"]
        disp = target["display_name"]
        model_id = target["model_id"]

        existing_match = next((r for r in benchmark_record["results"] if r.get("name") == name and r.get("success")), None)
        if existing_match and not args.force:
            print(f"\n[{i}/{total_models}] [SKIPPED] {disp} already completed successfully.")
            continue

        print(f"\n[{i}/{total_models}] [RUNNING] {disp} ({model_id})...")

        try:
            m_res = await run_debate_benchmark_for_model(
                target,
                paid_key,
                settings,
                eurusd_ctx,
                eurusd_fs,
                trap_ctx,
                trap_bull,
                trap_bear,
            )

            # Replace or append result
            benchmark_record["results"] = [r for r in benchmark_record["results"] if r.get("name") != name]
            benchmark_record["results"].append(m_res)

            # Save intermediate JSON
            with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(benchmark_record, f, indent=2)

            # Generate intermediate Markdown report
            md_content = build_markdown_report(benchmark_record)
            with open(MARKDOWN_OUTPUT_PATH, "w", encoding="utf-8") as f:
                f.write(md_content)

            print(f"      [✓] Completed and saved checkpoint for {disp}")

        except Exception as e:
            print(f"      [!] ERROR during benchmark for {disp}: {e}")
            import traceback
            traceback.print_exc()

    # Final report generation
    final_md = build_markdown_report(benchmark_record)
    with open(MARKDOWN_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(final_md)

    print("\n" + "=" * 75)
    print(f"[✓] ALL DEBATE BENCHMARKS COMPLETED!")
    print(f"[*] JSON Results: {JSON_OUTPUT_PATH}")
    print(f"[*] Markdown Report: {MARKDOWN_OUTPUT_PATH}")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
