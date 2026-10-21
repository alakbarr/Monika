# ==============================================================================
# File: scripts/evaluate_gate_filter_pnl.py
# ==============================================================================

"""
Measure what the Phase 1 permission gates do to realized profitability.

Every historical trade proposal is settled against the stored H1 candles with
the repository's own :class:`OutcomeEvaluator` (SL/TP first touch, spread,
slippage and swap), and then admitted or rejected twice:

* BASELINE  - the pre-Phase-1 rules (quantitative confidence >= 0.30, LLM
  confluence/priced-in scorecard, R:R >= 1.30).
* PHASE 1   - the rules that are shipped today (explicit quant scorecard with
  R:R >= 1.50 and confidence >= 0.60, LLM scorecard, evidence store gate).

The comparison answers the question the funnel report cannot: does the
stricter filter keep losers out, or does it just reduce activity?

Usage:
    python scripts/evaluate_gate_filter_pnl.py
    python scripts/evaluate_gate_filter_pnl.py --source json backups/.../pg_asset_analysis.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from monika.application.backtest.outcome_evaluator import OutcomeEvaluator
from monika.core.config.risk_defaults import (
    DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE,
    DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE,
    DEFAULT_MIN_RR_RATIO,
)
from monika.core.risk.quant_scorecard import (
    build_quant_scorecard,
    evaluate_analysis_scorecard,
    is_quantitative_source,
    validate_quant_scorecard,
)
from monika.infrastructure.database.models import BacktestTrade

OLD_MIN_RR = 1.3
OLD_MIN_QUANT_CONFIDENCE = 0.30
OLD_MIN_LLM_CONFIDENCE = 0.50


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _entry_price(row: dict[str, Any]) -> float | None:
    entry = row.get("entry_price")
    if entry is not None:
        try:
            value = float(entry)
            if value > 0:
                return value
        except TypeError, ValueError:
            pass
    zone = row.get("entry_zone")
    if isinstance(zone, str):
        try:
            zone = json.loads(zone)
        except TypeError, ValueError:
            return None
    if isinstance(zone, dict):
        try:
            value = float(zone.get("price", 0.0))
        except TypeError, ValueError:
            return None
        return value if value > 0 else None
    return None


def _is_quant_row(row: dict[str, Any]) -> bool:
    """Pre-Phase-1 detection: quantitative sources were detected by strategy id too."""
    source = str(row.get("decision_source") or "")
    return is_quantitative_source(source) or source == "concordant" or bool(row.get("source_strategy_id"))


def _baseline_admitted(row: dict[str, Any]) -> bool:
    """The rules that were in force before Phase 1."""
    confidence = row.get("confidence")
    try:
        confidence = float(confidence)
    except TypeError, ValueError:
        return False

    if _is_quant_row(row):
        if confidence < OLD_MIN_QUANT_CONFIDENCE:
            return False
    else:
        if confidence < OLD_MIN_LLM_CONFIDENCE:
            return False
        confluence = row.get("confluence_score")
        priced_in = row.get("priced_in_score")
        if confluence is None or priced_in is None:
            return False
        if float(priced_in) >= 8:
            return False
        if float(confluence) < DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE:
            return False

    return _rr_ok(row, OLD_MIN_RR)


def _rr_ok(row: dict[str, Any], min_rr: float) -> bool:
    entry = _entry_price(row)
    stop = row.get("stop_loss")
    target = row.get("take_profit")
    if entry is None or stop is None or target is None:
        return False
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return False
    return abs(float(target) - float(entry)) / risk >= min_rr


def _confidence_ok(row: dict[str, Any]) -> bool:
    """Confidence floors: 0.60 for quantitative proposals, 0.50 for LLM ones."""
    confidence = row.get("confidence")
    try:
        confidence = float(confidence)
    except TypeError, ValueError:
        return False
    floor = DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE if _is_quant_row(row) else OLD_MIN_LLM_CONFIDENCE
    return confidence >= floor


def _scorecard_admitted(row: dict[str, Any]) -> tuple[bool, str]:
    """The explicit scorecard requirement, using the shipped helper."""
    entry = _entry_price(row)
    stop = row.get("stop_loss")
    target = row.get("take_profit")
    source = str(row.get("decision_source") or "")

    scorecard = None
    if is_quantitative_source(source) or source == "concordant":
        scorecard = build_quant_scorecard(
            strategy_id=row.get("source_strategy_id"),
            direction=row.get("decision"),
            confidence=row.get("confidence"),
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
        )

    return evaluate_analysis_scorecard(
        decision_source=source,
        quant_scorecard=scorecard,
        confluence_score=row.get("confluence_score"),
        priced_in_score=row.get("priced_in_score"),
        min_confidence=DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE,
        min_rr_ratio=DEFAULT_MIN_RR_RATIO,
        min_confluence=DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE,
    )


def _phase1_admitted(row: dict[str, Any], enforce_evidence: bool) -> tuple[bool, str]:
    """The complete Phase 1 contract: R:R, confidence floor, scorecard, evidence."""
    if not _rr_ok(row, DEFAULT_MIN_RR_RATIO):
        return False, f"R:R below {DEFAULT_MIN_RR_RATIO}"
    if not _confidence_ok(row):
        return False, "confidence below floor"
    passed, reason = _scorecard_admitted(row)
    if not passed:
        return False, reason
    if enforce_evidence and not _evidence_ok(row.get("source_strategy_id")):
        return False, "evidence store rejected strategy"
    return True, "admitted"


def _ladder_admitted(row: dict[str, Any], stage: str, enforce_evidence: bool) -> bool:
    """Ablation ladder: each stage adds one Phase 1 gate on top of the previous."""
    if stage == "baseline":
        return _baseline_admitted(row)
    if stage == "rr":
        return _baseline_admitted(row) and _rr_ok(row, DEFAULT_MIN_RR_RATIO)
    if stage == "confidence":
        return _baseline_admitted(row) and _rr_ok(row, DEFAULT_MIN_RR_RATIO) and _confidence_ok(row)
    if stage == "scorecard":
        return (
            _baseline_admitted(row)
            and _rr_ok(row, DEFAULT_MIN_RR_RATIO)
            and _confidence_ok(row)
            and _scorecard_admitted(row)[0]
        )
    if stage == "evidence":
        return _phase1_admitted(row, enforce_evidence=True)[0]
    raise ValueError(f"unknown stage {stage}")


async def _load_rows(source: str, path: str | None) -> list[dict[str, Any]]:
    if source == "json":
        if not path:
            raise SystemExit("--source json requires --path")
        return json.loads(Path(path).read_text(encoding="utf-8"))

    from sqlalchemy import select

    from monika.infrastructure.database.db import get_session
    from monika.infrastructure.database.models import AssetAnalysis

    async with get_session(read_only=True) as session:
        rows = (await session.execute(select(AssetAnalysis))).scalars().all()
    return [
        {
            "symbol": r.symbol,
            "generated_at": r.generated_at,
            "decision": r.decision,
            "confidence": r.confidence,
            "entry_zone": r.entry_zone,
            "stop_loss": r.stop_loss,
            "take_profit": r.take_profit,
            "confluence_score": r.confluence_score,
            "priced_in_score": r.priced_in_score,
            "decision_source": r.decision_source,
            "source_strategy_id": r.source_strategy_id,
        }
        for r in rows
    ]


def _evidence_ok(strategy_id: str | None) -> bool:
    if not strategy_id:
        return True
    try:
        from monika.domain.risk.ports import get_default_evidence_store

        store = get_default_evidence_store()
        if store is None:
            return False
        eligible, _reason = store.is_strategy_eligible_to_trade(strategy_id)
        return bool(eligible)
    except Exception:
        return False


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "n": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "total": 0.0,
            "ci": (0.0, 0.0),
        }
    pnls = [float(r["pnl_pct"]) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "n": len(rows),
        "win_rate": round(100.0 * len(wins) / len(rows), 1),
        "avg_pnl": round(sum(pnls) / len(rows), 3),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf"),
        "total": round(sum(pnls), 2),
        "ci": _bootstrap_ci(pnls),
    }


def _bootstrap_ci(pnls: list[float], iterations: int = 2000, seed: int = 20261021) -> tuple[float, float]:
    """95% bootstrap confidence interval of the mean PnL per trade."""
    if len(pnls) < 5:
        return (0.0, 0.0)
    import random

    rng = random.Random(seed)
    n = len(pnls)
    means = []
    for _ in range(iterations):
        sample = [pnls[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low = means[int(0.025 * iterations)]
    high = means[int(0.975 * iterations) - 1]
    return (round(low, 3), round(high, 3))


async def _run(args: argparse.Namespace) -> int:
    rows = await _load_rows(args.source, args.path)
    proposals = [r for r in rows if str(r.get("decision") or "").lower() in ("buy", "sell")]

    evaluator = OutcomeEvaluator(max_holding_hours=args.max_holding_hours)

    ladder_rows: dict[str, list[dict[str, Any]]] = {
        "baseline": [],
        "rr": [],
        "confidence": [],
        "scorecard": [],
        "evidence": [],
    }
    skipped = 0

    for row in proposals:
        entry_time = _parse_ts(row.get("generated_at"))
        entry = _entry_price(row)
        stop = row.get("stop_loss")
        target = row.get("take_profit")
        if entry_time is None or entry is None or stop is None or target is None:
            skipped += 1
            continue

        trade = BacktestTrade(
            symbol=str(row.get("symbol") or "").upper(),
            direction=str(row.get("decision") or "").lower(),
            entry_time=entry_time,
            entry_price=float(entry),
            stop_loss=float(stop),
            take_profit=float(target),
        )
        try:
            outcome = await evaluator.evaluate_trade(trade, apply_costs=True)
        except Exception as exc:  # noqa: BLE001 - one proposal must not abort the run
            print(f"  settlement failed for {trade.symbol}: {exc}")
            skipped += 1
            continue

        record = {
            "symbol": trade.symbol,
            "source": str(row.get("decision_source") or "unknown"),
            "strategy_id": row.get("source_strategy_id"),
            "pnl_pct": float(outcome.get("pnl_pct") or 0.0),
            "exit_reason": outcome.get("exit_reason"),
        }

        for stage in ladder_rows:
            if _ladder_admitted(row, stage, enforce_evidence=True):
                ladder_rows[stage].append(record)

    print("=" * 78)
    print("PHASE 1 GATE FILTER vs REALIZED PnL")
    print("=" * 78)
    print(f"proposals offered        : {len(proposals)}")
    print(f"settled                  : {len(proposals) - skipped} (skipped {skipped})")
    print(f"settlement model         : SL/TP first touch, {args.max_holding_hours}h max hold, spread+slippage+swap")
    print()

    stage_labels = (
        ("baseline", "1. BASELINE (pre-Phase-1)"),
        ("rr", "2. + R:R >= 1.50"),
        ("confidence", "3. + confidence floor 0.60"),
        ("scorecard", "4. + explicit scorecard"),
        ("evidence", "5. + evidence store (FULL)"),
    )
    baseline_stats = _stats(ladder_rows["baseline"])
    for stage, label in stage_labels:
        stats = _stats(ladder_rows[stage])
        low, high = stats["ci"]
        delta = ""
        if baseline_stats["n"]:
            delta = (
                f"  vs baseline: n {stats['n']}/{baseline_stats['n']}"
                f"  avg {stats['avg_pnl']} (CI {low}..{high})"
                f"  PF {stats['profit_factor']}"
            )
        print(f"{label}")
        print(
            f"   n={stats['n']:<6} win_rate={stats['win_rate']:<6}% avg_pnl={stats['avg_pnl']:<8} "
            f"PF={stats['profit_factor']:<8} total_pnl_pct={stats['total']:<8} CI[{low}..{high}]{delta}"
        )
    print()

    for stage, label in stage_labels:
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in ladder_rows[stage]:
            by_source[record["source"]].append(record)
        print(f"by source - {label}")
        for source, records in sorted(by_source.items()):
            stats = _stats(records)
            low, high = stats["ci"]
            print(
                f"   {source:<24} n={stats['n']:<6} wr={stats['win_rate']:<6}% "
                f"avg_pnl={stats['avg_pnl']:<8} PF={stats['profit_factor']:<8} CI[{low}..{high}]"
            )
        print()

    print("NOTE: PnL is per-trade percent of the risked distance (1% risk per trade),")
    print("      so total_pnl_pct approximates the compounded equity effect of the subset.")
    print("      CI is a 95% bootstrap interval of the mean PnL per trade; an interval")
    print("      that contains 0 means the subset is not statistically separated from break-even.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare realized PnL before and after the Phase 1 gates.")
    parser.add_argument("--source", choices=("live", "json"), default="live")
    parser.add_argument("--path", help="path to a JSON export of asset_analysis rows")
    parser.add_argument("--max-holding-hours", type=int, default=72)
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
