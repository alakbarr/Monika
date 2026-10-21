# ==============================================================================
# File: scripts/report_execution_funnel.py
# ==============================================================================

"""
Execution funnel report: where trade proposals die before the broker.

Replays the deterministic Phase 1 permission gates over historical
``AssetAnalysis`` records and reports how many proposals were offered and how
many were rejected by each gate. Read-only: never writes to the database.

Usage:
    python scripts/report_execution_funnel.py
    python scripts/report_execution_funnel.py --source json backups/.../pg_asset_analysis.json
    python scripts/report_execution_funnel.py --days 30 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from monika.core.config.risk_defaults import (
    DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE,
    DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE,
    DEFAULT_MIN_RR_RATIO,
)
from monika.core.risk.quant_scorecard import extract_quant_scorecard, is_quantitative_source
from monika.domain.risk.risk_gate import RiskGate

ACTIONABLE = ("buy", "sell")


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


def _settings() -> dict:
    try:
        from monika.core.config.settings import load_settings

        return load_settings() or {}
    except Exception:
        return {}


async def _load_live(days: int | None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from monika.infrastructure.database.db import get_session
    from monika.infrastructure.database.models import AssetAnalysis

    async with get_session(read_only=True) as session:
        stmt = select(AssetAnalysis)
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = stmt.where(AssetAnalysis.generated_at >= cutoff)
        rows = (await session.execute(stmt)).scalars().all()

    return [
        {
            "id": getattr(row, "id", None),
            "symbol": getattr(row, "symbol", None),
            "generated_at": getattr(row, "generated_at", None),
            "decision": getattr(row, "decision", None),
            "confidence": getattr(row, "confidence", None),
            "entry_price": getattr(row, "entry_price", None),
            "stop_loss": getattr(row, "stop_loss", None),
            "take_profit": getattr(row, "take_profit", None),
            "confluence_score": getattr(row, "confluence_score", None),
            "priced_in_score": getattr(row, "priced_in_score", None),
            "decision_source": getattr(row, "decision_source", None),
            "source_strategy_id": getattr(row, "source_strategy_id", None),
            "confluence_factors_json": getattr(row, "confluence_factors_json", None),
        }
        for row in rows
    ]


def _load_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} does not contain a list of analysis rows")
    return data


def _entry_price(row: dict[str, Any]) -> float | None:
    entry = row.get("entry_price")
    if entry is not None:
        try:
            return float(entry)
        except TypeError, ValueError:
            return None
    zone = row.get("entry_zone")
    if isinstance(zone, str):
        try:
            zone = json.loads(zone)
        except TypeError, ValueError:
            return None
    if isinstance(zone, dict):
        try:
            price = float(zone.get("price", 0.0))
        except TypeError, ValueError:
            return None
        return price if price > 0 else None
    return None


def _rr_ratio(row: dict[str, Any]) -> float | None:
    entry = _entry_price(row)
    stop = row.get("stop_loss")
    target = row.get("take_profit")
    if entry is None or stop is None or target is None:
        return None
    try:
        risk = abs(float(entry) - float(stop))
        reward = abs(float(target) - float(entry))
    except TypeError, ValueError:
        return None
    if risk <= 0:
        return None
    return reward / risk


async def _evaluate(rows: list[dict[str, Any]], settings: dict) -> dict[str, Any]:
    gate = RiskGate(settings)
    trading_cfg = settings.get("trading", {}) if isinstance(settings, dict) else {}
    risk_cfg = trading_cfg.get("risk", {}) if isinstance(trading_cfg, dict) else {}
    min_confidence = float(trading_cfg.get("auto_execute_min_confidence", DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE))
    min_rr = float(risk_cfg.get("min_rr_ratio", DEFAULT_MIN_RR_RATIO))
    min_confluence = int(trading_cfg.get("auto_execute_min_confluence", DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE))

    total = 0
    non_actionable = 0
    passed = 0
    reasons: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    missing_scorecard = 0

    for row in rows:
        total += 1
        decision = str(row.get("decision") or "").lower()
        source = str(row.get("decision_source") or "unknown")
        if decision not in ACTIONABLE:
            non_actionable += 1
            by_source[source]["not_actionable"] += 1
            continue

        row_reasons: list[str] = []

        class _Analysis:
            pass

        analysis = _Analysis()
        for key, value in row.items():
            setattr(analysis, key, value)

        scorecard_ok, scorecard_reason = await gate._check_analysis_quality_scores(analysis, session=None)
        if not scorecard_ok:
            row_reasons.append(f"scorecard: {scorecard_reason}")

        if extract_quant_scorecard(analysis) is None and is_quantitative_source(source):
            missing_scorecard += 1

        evidence_ok, evidence_reason = await gate._check_evidence_gate(
            None, str(row.get("symbol") or ""), analysis=analysis
        )
        if not evidence_ok:
            row_reasons.append(f"evidence: {evidence_reason}")

        ratio = _rr_ratio(row)
        if ratio is not None and ratio < min_rr:
            row_reasons.append(f"rr: R:R {ratio:.2f} < {min_rr:.2f}")

        if is_quantitative_source(source):
            confidence = row.get("confidence")
            try:
                confidence_value = float(confidence)
            except TypeError, ValueError:
                confidence_value = None
            if confidence_value is None or confidence_value < min_confidence:
                row_reasons.append(f"confidence: {confidence} < {min_confidence:.2f}")

        if row_reasons:
            for reason in row_reasons:
                key = reason.split(":")[0].strip()
                reasons[key] += 1
                by_source[source][key] += 1
            by_source[source]["rejected"] += 1
        else:
            passed += 1
            by_source[source]["passed"] += 1

    return {
        "total_rows": total,
        "not_actionable": non_actionable,
        "actionable": total - non_actionable,
        "passed": passed,
        "rejected": (total - non_actionable) - passed,
        "missing_quant_scorecard": missing_scorecard,
        "rejection_reasons": dict(reasons.most_common()),
        "by_source": {src: dict(counts) for src, counts in sorted(by_source.items())},
        "thresholds": {
            "min_rr_ratio": min_rr,
            "min_confidence": min_confidence,
            "min_confluence": min_confluence,
        },
    }


def _print_report(report: dict[str, Any]) -> None:
    thresholds = report["thresholds"]
    print("=" * 72)
    print("EXECUTION FUNNEL - Phase 1 permission gates")
    print("=" * 72)
    print(f"rows scanned            : {report['total_rows']}")
    print(f"actionable proposals    : {report['actionable']}")
    print(f"passed all gates        : {report['passed']}")
    print(f"rejected                : {report['rejected']}")
    print(f"quant rows w/o scorecard: {report['missing_quant_scorecard']}")
    print(
        f"thresholds              : R:R>={thresholds['min_rr_ratio']} "
        f"confidence>={thresholds['min_confidence']} "
        f"confluence>={thresholds['min_confluence']}"
    )
    print()
    print("rejections by gate:")
    for reason, count in report["rejection_reasons"].items():
        print(f"  {count:5d}  {reason}")
    print()
    print("by decision source:")
    for source, counts in report["by_source"].items():
        detail = ", ".join(f"{k}={v}" for k, v in counts.items())
        print(f"  {source:<24} {detail}")


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Report the execution funnel for Phase 1 gates.")
    parser.add_argument(
        "--source",
        choices=("live", "json"),
        default="live",
        help="read the live database (default) or a JSON export of asset_analysis rows",
    )
    parser.add_argument("--path", help="path to a JSON export (required with --source json)")
    parser.add_argument("--days", type=int, default=None, help="only rows from the last N days (live only)")
    parser.add_argument("--json", action="store_true", help="print the raw report as JSON")
    args = parser.parse_args()

    if args.source == "json":
        if not args.path:
            parser.error("--source json requires --path")
        rows = _load_json(Path(args.path))
    else:
        rows = await _load_live(args.days)

    report = await _evaluate(rows, _settings())
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
