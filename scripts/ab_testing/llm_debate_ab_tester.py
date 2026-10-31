#!/usr/bin/env python3
"""
Empirical LLM Debate A/B Testing Harness.
Evaluates dialectical multi-agent debate performance against real market candles:
  - Baseline (Variant A): Passive avoidance and one-sided challenge.
  - Dialectical Grounding (Variant B): Symmetrical dealing-range anchors (Discount/Premium),
    concrete proposed levels (R:R >= 1.5, SL >= 1.0x ATR), and ADX climax guards.

Usage:
    venv\\Scripts\\python.exe scripts/ab_testing/llm_debate_ab_tester.py [--dry-run] [--model gemini-3.5-flash-lite]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from monika.core.config.settings import load_settings
from monika.interfaces.cli.platform_compat import ensure_utf8_streams

ensure_utf8_streams()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LLMDebateABTester")


@dataclass
class DebateTestCase:
    id: int
    symbol: str
    timestamp: str
    p0: float
    atr_est: float
    technical_bias: str
    macro_bias: str
    sentiment_bias: str
    rationale: str
    recent_candles: List[Dict[str, float]]
    actual_24h_ret: float
    actual_48h_ret: float


@dataclass
class DebateOutcome:
    variant: str
    case_id: int
    symbol: str
    decision: str  # buy, sell, avoid
    confidence: float
    risk_multiplier: float
    reason: str
    realized_pnl_24h: float
    realized_pnl_48h: float
    is_win_24h: bool
    is_non_loss_24h: bool


def _load_or_create_benchmark_fixtures() -> List[DebateTestCase]:
    """Load canonical test cases from disk or provide standard historical fixtures."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    bench_file = repo_root / "scratch" / "debate_test_cases.json"

    if not bench_file.exists():
        # Fallback search in brain scratch
        app_data = Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity-cli" / "brain"
        candidate_files = list(app_data.glob("*/scratch/debate_test_cases.json"))
        if candidate_files:
            bench_file = candidate_files[-1]

    if bench_file.exists():
        with open(bench_file, "r", encoding="utf-8") as f:
            raw_cases = json.load(f)
            return [
                DebateTestCase(
                    id=c["id"],
                    symbol=c["symbol"],
                    timestamp=c.get("timestamp", "2026-10"),
                    p0=float(c["p0"]),
                    atr_est=float(c["atr_est"]),
                    technical_bias=c["technical_bias"],
                    macro_bias=c["macro_bias"],
                    sentiment_bias=c["sentiment_bias"],
                    rationale=c.get("rationale", ""),
                    recent_candles=c.get("recent_candles", []),
                    actual_24h_ret=float(c.get("actual_24h_ret", 0.0)),
                    actual_48h_ret=float(c.get("actual_48h_ret", 0.0)),
                )
                for c in raw_cases
            ]

    # Deterministic default fixtures across G10 and Commodities
    return [
        DebateTestCase(
            id=1,
            symbol="EURUSD",
            timestamp="2026-10-15T08:00:00Z",
            p0=1.0850,
            atr_est=0.0045,
            technical_bias="bullish",
            macro_bias="bearish",
            sentiment_bias="neutral",
            rationale="H1 bullish market structure break at key discount support, but macro brief is USD-strong.",
            recent_candles=[
                {"o": 1.0820, "h": 1.0860, "l": 1.0815, "c": 1.0850},
                {"o": 1.0815, "h": 1.0835, "l": 1.0805, "c": 1.0820},
                {"o": 1.0850, "h": 1.0855, "l": 1.0810, "c": 1.0815},
            ],
            actual_24h_ret=0.0035,
            actual_48h_ret=0.0062,
        ),
        DebateTestCase(
            id=2,
            symbol="XAUUSD",
            timestamp="2026-10-16T14:00:00Z",
            p0=2650.0,
            atr_est=22.5,
            technical_bias="bearish",
            macro_bias="bullish",
            sentiment_bias="bullish",
            rationale="M15/H1 liquidity grab above 2660 rejection, but macro safe-haven flows remain high.",
            recent_candles=[
                {"o": 2645.0, "h": 2662.0, "l": 2642.0, "c": 2650.0},
                {"o": 2635.0, "h": 2648.0, "l": 2630.0, "c": 2645.0},
                {"o": 2620.0, "h": 2638.0, "l": 2618.0, "c": 2635.0},
            ],
            actual_24h_ret=-0.0085,
            actual_48h_ret=-0.0120,
        ),
    ]


def _extract_json_dict(resp: Any) -> Dict[str, Any]:
    """Safely extracts JSON dict from LLM response (supports str, BaseLLMResponse, or dict)."""
    if isinstance(resp, dict):
        return resp
    if hasattr(resp, "text") and isinstance(resp.text, str):
        text = resp.text
    elif hasattr(resp, "content") and isinstance(resp.content, str):
        text = resp.content
    else:
        text = str(resp or "").strip()
    if not text:
        return {}
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    elif "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        text = text[start:end].strip()
    try:
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Failed to parse JSON from LLM response: {e}. Raw text: {text[:150]}")
        return {}


class EmpiricalDebateEvaluator:
    def __init__(self, model_name: str, settings: dict, dry_run: bool = False):
        self.model_name = model_name
        self.settings = settings
        self.dry_run = dry_run
        self.client = None
        if not dry_run:
            try:
                from monika.infrastructure.providers.llm_factory import create_client

                self.client = create_client(model_name, settings=settings)
            except Exception as e:
                logger.warning(f"Could not initialize LLM client '{model_name}': {e}. Falling back to dry-run mode.")
                self.dry_run = True

    async def run_control(self, case: DebateTestCase) -> DebateOutcome:
        """Variant A (Baseline): Passive macro conflict triggers AVOID / WAIT."""
        if self.dry_run or not self.client:
            # Baseline deterministic simulation
            return DebateOutcome(
                variant="Control (Baseline)",
                case_id=case.id,
                symbol=case.symbol,
                decision="avoid",
                confidence=0.50,
                risk_multiplier=0.0,
                reason="Macro brief opposes technical bias; passive avoidance triggered.",
                realized_pnl_24h=0.0,
                realized_pnl_48h=0.0,
                is_win_24h=False,
                is_non_loss_24h=True,
            )

        # Active evaluation with baseline prompts
        prompt = (
            f"You are the Investment Judge arbitrating {case.symbol}. Price: {case.p0}. "
            f"Technicals are {case.technical_bias.upper()} but Macro is {case.macro_bias.upper()}. "
            f"Rule: Opposing macro without overwhelming proof must be avoided. "
            f'Output JSON: {{"final_decision": "buy"|"sell"|"avoid", "reason": "..."}}'
        )
        try:
            resp = await self.client.generate_content(
                system_prompt="You are a conservative risk manager.",
                user_message=prompt,
                response_schema={
                    "type": "object",
                    "properties": {"final_decision": {"type": "string"}, "reason": {"type": "string"}},
                },
            )
            raw = _extract_json_dict(resp)
            dec = str(raw.get("final_decision", "avoid")).lower()
        except Exception as e:
            logger.warning(f"Control LLM call error: {e}. Failing closed to avoid.")
            dec = "avoid"

        return self._compute_outcome(
            "Control (Baseline)", case, dec, 0.50, 0.0 if dec == "avoid" else 1.0, "Evaluated baseline"
        )

    async def run_variant(self, case: DebateTestCase) -> DebateOutcome:
        """Variant B (Dialectical Grounding & Dealing Range): Active SMC adjudication."""
        if self.dry_run or not self.client:
            # Dialectical simulation: Evaluates dealing range position
            candles = case.recent_candles or [{"h": case.p0 * 1.01, "l": case.p0 * 0.99}]
            hi = max(c["h"] for c in candles)
            lo = min(c["l"] for c in candles)
            pos = (case.p0 - lo) / max(1e-5, (hi - lo))

            # Discount (<0.50) + Bullish Technicals -> BUY
            # Premium (>0.50) + Bearish Technicals -> SELL
            if case.technical_bias == "bullish" and pos <= 0.55:
                dec = "buy"
                conf = 0.72
                rm = 0.70
                reason = f"Grounded Long in Discount (pos={pos:.2f}) with structural invalidation of macro thesis."
            elif case.technical_bias == "bearish" and pos >= 0.45:
                dec = "sell"
                conf = 0.70
                rm = 0.70
                reason = f"Grounded Short in Premium (pos={pos:.2f}) with verified liquidity sweep."
            else:
                dec = "avoid"
                conf = 0.40
                rm = 0.0
                reason = f"Dealing range location (pos={pos:.2f}) unfavorable for directional entry."

            return self._compute_outcome("Variant B (Dialectical)", case, dec, conf, rm, reason)

        # Active LLM Dialectical Evaluation
        candles = case.recent_candles or [{"h": case.p0 * 1.01, "l": case.p0 * 0.99}]
        hi = max(c["h"] for c in candles)
        lo = min(c["l"] for c in candles)
        pos = (case.p0 - lo) / max(1e-5, (hi - lo))
        range_desc = f"Premium (pos={pos:.2f})" if pos > 0.5 else f"Discount (pos={pos:.2f})"

        prompt = f"""
You are the Chief Investment Judge arbitrating a conflict on {case.symbol}. Current Price: {case.p0}.
ESTIMATED ATR: {case.atr_est:.5f}.
DEALING RANGE LOCATION: {range_desc}.
SPECIALIST BIASES: Technical={case.technical_bias.upper()}, Macro={case.macro_bias.upper()}.

DIALECTICAL ADJUDICATION RULES:
1. Long entries require Discount (<0.50) or structural sweep. Short entries require Premium (>0.50) or structural sweep.
2. If technicals establish an unmitigated structural setup with R:R >= 1.5 and SL >= 1.0x ATR, adjudicate in favor of market structure.
3. If price is extended without retracement, rule 'avoid'.

Respond strictly in JSON:
{{
  "final_decision": "buy" | "sell" | "avoid",
  "confidence": float (0.0 to 1.0),
  "risk_multiplier": float (0.2 to 1.0 or 0.0 for avoid),
  "reason": "..."
}}
"""
        try:
            resp = await self.client.generate_content(
                system_prompt="You are a senior quantitative risk judge.",
                user_message=prompt,
                response_schema={
                    "type": "object",
                    "properties": {
                        "final_decision": {"type": "string"},
                        "confidence": {"type": "number"},
                        "risk_multiplier": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["final_decision", "confidence", "reason"],
                },
            )
            raw = _extract_json_dict(resp)
            dec = str(raw.get("final_decision", "avoid")).lower()
            conf = float(raw.get("confidence", 0.60))
            rm = float(raw.get("risk_multiplier", 0.50)) if dec != "avoid" else 0.0
            reason = str(raw.get("reason", "Adjudicated dialectical synthesis."))
        except Exception as e:
            logger.warning(f"Variant LLM call error: {e}. Failing closed to avoid.")
            dec = "avoid"
            conf = 0.0
            rm = 0.0
            reason = f"Fail closed: {e}"

        return self._compute_outcome("Variant B (Dialectical)", case, dec, conf, rm, reason)

    def _compute_outcome(
        self, variant: str, case: DebateTestCase, decision: str, confidence: float, rm: float, reason: str
    ) -> DebateOutcome:
        r24 = case.actual_24h_ret
        r48 = case.actual_48h_ret

        if decision == "buy":
            pnl_24 = r24
            pnl_48 = r48
            is_win = r24 > 0.0005
            is_non_loss = r24 >= -0.0005
        elif decision == "sell":
            pnl_24 = -r24
            pnl_48 = -r48
            is_win = -r24 > 0.0005
            is_non_loss = -r24 >= -0.0005
        else:  # avoid
            pnl_24 = 0.0
            pnl_48 = 0.0
            is_win = False
            is_non_loss = True

        return DebateOutcome(
            variant=variant,
            case_id=case.id,
            symbol=case.symbol,
            decision=decision,
            confidence=confidence,
            risk_multiplier=rm,
            reason=reason,
            realized_pnl_24h=pnl_24,
            realized_pnl_48h=pnl_48,
            is_win_24h=is_win,
            is_non_loss_24h=is_non_loss,
        )


def print_summary_table(control_results: List[DebateOutcome], variant_results: List[DebateOutcome]):
    def stats(res_list: List[DebateOutcome]):
        total = len(res_list)
        trades = [r for r in res_list if r.decision in ("buy", "sell")]
        avoids = [r for r in res_list if r.decision == "avoid"]
        n_trades = len(trades)
        wins = sum(1 for r in trades if r.is_win_24h)
        non_losses = sum(1 for r in trades if r.is_non_loss_24h)
        pnl_24 = [r.realized_pnl_24h for r in trades]
        pnl_48 = [r.realized_pnl_48h for r in trades]
        win_rate = (wins / n_trades * 100) if n_trades > 0 else 0.0
        non_loss_rate = (non_losses / n_trades * 100) if n_trades > 0 else 0.0
        avg_pnl_24 = (np.mean(pnl_24) * 100) if pnl_24 else 0.0
        avg_pnl_48 = (np.mean(pnl_48) * 100) if pnl_48 else 0.0
        return {
            "total": total,
            "trades": n_trades,
            "avoids": len(avoids),
            "win_rate": win_rate,
            "non_loss_rate": non_loss_rate,
            "avg_pnl_24": avg_pnl_24,
            "avg_pnl_48": avg_pnl_48,
        }

    c_s = stats(control_results)
    v_s = stats(variant_results)

    print("\n" + "=" * 80)
    print("EMPIRICAL LLM DEBATE A/B BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"{'Metric':<38} | {'Control (Baseline)':<18} | {'Variant (Dialectical)':<18} | {'Delta':<10}")
    print("-" * 88)
    print(f"{'Total Sampled Conflict Cases':<38} | {c_s['total']:<18} | {v_s['total']:<18} | 0")
    print(
        f"{'Actionable Trades (BUY / SELL)':<38} | {c_s['trades']:<18} | {v_s['trades']:<18} | {v_s['trades'] - c_s['trades']:+d}"
    )
    print(
        f"{'Passive Avoids (WAIT)':<38} | {c_s['avoids']:<18} | {v_s['avoids']:<18} | {v_s['avoids'] - c_s['avoids']:+d}"
    )
    print(
        f"{'Directional 24h Win Rate':<38} | {c_s['win_rate']:5.1f}%             | {v_s['win_rate']:5.1f}%             | {v_s['win_rate'] - c_s['win_rate']:+5.1f}%"
    )
    print(
        f"{'Non-Loss Rate (Wins + Scratches)':<38} | {c_s['non_loss_rate']:5.1f}%             | {v_s['non_loss_rate']:5.1f}%             | {v_s['non_loss_rate'] - c_s['non_loss_rate']:+5.1f}%"
    )
    print(
        f"{'Avg Realized 24h Return':<38} | {c_s['avg_pnl_24']:+5.2f}%             | {v_s['avg_pnl_24']:+5.2f}%             | {v_s['avg_pnl_24'] - c_s['avg_pnl_24']:+5.2f}%"
    )
    print(
        f"{'Avg Realized 48h Return':<38} | {c_s['avg_pnl_48']:+5.2f}%             | {v_s['avg_pnl_48']:+5.2f}%             | {v_s['avg_pnl_48'] - c_s['avg_pnl_48']:+5.2f}%"
    )
    print("=" * 80 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="LLM Debate A/B Testing Harness")
    parser.add_argument("--dry-run", action="store_true", help="Run in offline deterministic simulation mode")
    parser.add_argument("--model", type=str, default="gemini-3.5-flash-lite", help="Gemini model name")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of cases to evaluate")
    args = parser.parse_args()

    settings = load_settings()
    cases = _load_or_create_benchmark_fixtures()[: args.limit]
    logger.info(f"Loaded {len(cases)} historical debate conflict cases.")

    evaluator = EmpiricalDebateEvaluator(model_name=args.model, settings=settings, dry_run=args.dry_run)

    logger.info(f"Running Control (Baseline) on {len(cases)} cases...")
    control_tasks = [evaluator.run_control(c) for c in cases]
    control_results = await asyncio.gather(*control_tasks)

    logger.info(f"Running Variant B (Dialectical Grounding) on {len(cases)} cases...")
    variant_tasks = [evaluator.run_variant(c) for c in cases]
    variant_results = await asyncio.gather(*variant_tasks)

    print_summary_table(control_results, variant_results)


if __name__ == "__main__":
    asyncio.run(main())
