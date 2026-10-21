# ==============================================================================
# File: scripts/bootstrap_strategy_evidence.py
# ==============================================================================

"""
Bootstrap the strategy evidence store from real, isolated backtest evidence.

The evidence store (``data/strategy_evidence_store.json``) is the only source of
promotion truth since Phase 1, but it had no producer: every strategy was
therefore permanently ineligible. This script closes that gap by running the
existing zero-lookahead :class:`IsolatedStrategyBacktestHarness` per strategy
and recording only the evidence that passes the store's own hurdles:

* a minimum sample size (default 20 closed trades),
* a positive expectancy (profit factor > 1 and positive total return),
* a sizing-corrected breakeven above the broker fee floor (3.0 bps).

Strategies that fail any hurdle are left WITHOUT evidence, so they stay
experimental and cannot be promoted. Nothing is fabricated: every number comes
from the historical candles stored in the database.

Usage:
    python scripts/bootstrap_strategy_evidence.py
    python scripts/bootstrap_strategy_evidence.py --dry-run
    python scripts/bootstrap_strategy_evidence.py --min-trades 30 --include-synthesized 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from monika.application.analysis.strategies.evidence_store import (
    DEFAULT_EVIDENCE_FILE,
    StrategyEvidenceStore,
)
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import PriceOHLCV
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BootstrapEvidence")

MIN_BREAKEVEN_BPS = 3.0


async def _available_symbols(session) -> set[str]:
    stmt = select(PriceOHLCV.symbol).distinct()
    rows = (await session.execute(stmt)).scalars().all()
    return {str(s).upper() for s in rows if s}


def _primary_symbol(strategy_cls, available: set[str]) -> str | None:
    symbols = [str(s).upper() for s in (getattr(strategy_cls, "applicable_symbols", None) or [])]
    for symbol in sorted(symbols):
        if symbol in available:
            return symbol
    return None


def _target_symbols(strategy_cls, available: set[str], single: bool) -> list[str]:
    symbols = sorted({str(s).upper() for s in (getattr(strategy_cls, "applicable_symbols", None) or [])} & available)
    if single:
        primary = _primary_symbol(strategy_cls, available)
        return [primary] if primary else []
    return symbols


def _pool_metrics(per_symbol: dict[str, Any]) -> dict[str, Any]:
    """Pool per-symbol harness metrics using the raw per-trade returns."""
    returns: list[float] = []
    sharpe_weighted = 0.0
    win_rate_weighted = 0.0
    max_dd = 0.0
    errors = 0
    error_samples: list[str] = []
    for symbol, metrics in per_symbol.items():
        returns.extend(float(r) for r in metrics.trade_returns)
        weight = float(metrics.total_trades)
        sharpe_weighted += float(metrics.sharpe_ratio) * weight
        win_rate_weighted += float(metrics.win_rate_pct) * weight
        max_dd = max(max_dd, float(metrics.max_drawdown_pct))
        errors += int(getattr(metrics, "evaluation_errors", 0) or 0)
        for sample in getattr(metrics, "error_samples", []) or []:
            if sample not in error_samples:
                error_samples.append(sample)

    total_trades = len(returns)
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit and 99.0 or 0.0)
    return {
        "total_trades": total_trades,
        "gross_return": sum(returns),
        "profit_factor": float(profit_factor),
        "win_rate_pct": (win_rate_weighted / total_trades) if total_trades else 0.0,
        "sharpe_ratio": (sharpe_weighted / total_trades) if total_trades else 0.0,
        "max_drawdown_pct": max_dd,
        "evaluation_errors": errors,
        "error_samples": error_samples,
    }


async def _evaluate_strategy(strategy_cls, symbol: str, lookback: int, settings: dict) -> Any:
    harness = IsolatedStrategyBacktestHarness(strategy_cls=strategy_cls, symbol=symbol, settings=settings)
    async with get_session(read_only=True) as session:
        return await harness.run_simulation(session=session, lookback_candles=lookback)


def _load_synthesized(limit: int) -> dict[str, Any]:
    """Import synthesized alpha strategies from disk (bounded, best effort)."""
    import importlib.util

    loaded: dict[str, Any] = {}
    synth_dir = StrategyRegistry.SYNTHESIZED_DIR
    if not synth_dir.is_dir():
        return loaded
    for path in sorted(synth_dir.glob("alpha_*.py"))[:limit]:
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for attr in vars(module).values():
                if isinstance(attr, type) and getattr(attr, "strategy_id", None) and attr.strategy_id == path.stem:
                    loaded[path.stem] = attr
                    break
        except Exception as exc:  # noqa: BLE001 - a broken alpha must not abort the run
            logger.warning("Failed to import synthesized strategy %s: %s", path.stem, exc)
    return loaded


async def _run(args: argparse.Namespace) -> int:
    from monika.core.config.settings import load_settings

    settings = load_settings() or {}
    store = StrategyEvidenceStore(DEFAULT_EVIDENCE_FILE)

    async with get_session(read_only=True) as session:
        available = await _available_symbols(session)

    registry = dict(StrategyRegistry._registry)
    if args.include_synthesized:
        registry.update(_load_synthesized(args.include_synthesized))

    results: list[dict[str, Any]] = []
    recorded = 0

    for strategy_id, strategy_cls in sorted(registry.items()):
        if strategy_id in StrategyRegistry.QUARANTINED_STRATEGY_IDS:
            results.append(
                {
                    "strategy_id": strategy_id,
                    "status": "skipped",
                    "reason": "quarantined (quarantine outranks evidence)",
                }
            )
            continue

        symbols = _target_symbols(strategy_cls, available, args.single_symbol)
        if not symbols:
            results.append(
                {
                    "strategy_id": strategy_id,
                    "status": "skipped",
                    "reason": "no applicable symbol with stored price history",
                }
            )
            continue

        per_symbol: dict[str, Any] = {}
        for symbol in symbols:
            try:
                per_symbol[symbol] = await _evaluate_strategy(strategy_cls, symbol, args.lookback, settings)
            except Exception as exc:  # noqa: BLE001 - one symbol must not abort the strategy
                logger.warning("Harness failed for %s on %s: %s", strategy_id, symbol, exc)

        if not per_symbol:
            results.append({"strategy_id": strategy_id, "status": "error", "reason": "harness produced no metrics"})
            continue

        pooled = _pool_metrics(per_symbol)
        trades = int(pooled["total_trades"])
        profit_factor = float(pooled["profit_factor"])
        gross_return = float(pooled["gross_return"])
        symbol_label = symbols[0] if len(symbols) == 1 else f"MULTI({len(symbols)})"

        if pooled["evaluation_errors"]:
            # A strategy that raised while being evaluated has no evidence at all.
            # Recording "no edge" for it would hide a broken strategy behind a
            # performance verdict, so it is reported as an error instead.
            results.append(
                {
                    "strategy_id": strategy_id,
                    "symbol": symbol_label,
                    "status": "error",
                    "reason": (
                        f"{pooled['evaluation_errors']} evaluation errors, first: "
                        f"{pooled['error_samples'][0] if pooled['error_samples'] else 'unknown'}"
                    ),
                }
            )
            continue

        if trades < args.min_trades:
            results.append(
                {
                    "strategy_id": strategy_id,
                    "symbol": symbol_label,
                    "trades": trades,
                    "status": "rejected",
                    "reason": f"sample too small ({trades} < {args.min_trades} trades)",
                }
            )
            continue

        if profit_factor <= 1.0 or gross_return <= 0:
            results.append(
                {
                    "strategy_id": strategy_id,
                    "symbol": symbol_label,
                    "trades": trades,
                    "status": "rejected",
                    "reason": f"no positive edge (PF {profit_factor:.2f}, return {gross_return * 100:.2f}%)",
                }
            )
            continue

        window_end = await _latest_bar_end(symbols[0])

        if args.dry_run:
            from monika.application.analysis.strategies.evidence_store import (
                compute_sizing_corrected_breakeven_bps,
            )

            breakeven = compute_sizing_corrected_breakeven_bps(
                gross_return=gross_return,
                total_trades=trades,
                avg_position_size=1.0,
                max_concurrent_positions=1,
            )
            results.append(
                {
                    "strategy_id": strategy_id,
                    "symbol": symbol_label,
                    "trades": trades,
                    "status": "would_record" if breakeven >= MIN_BREAKEVEN_BPS else "rejected",
                    "reason": f"PF {profit_factor:.2f}, breakeven {breakeven:.2f} bps",
                }
            )
            continue

        evidence = store.record_evidence(
            strategy_id=strategy_id,
            symbol=symbol_label,
            timeframe="H1",
            data_window_end=window_end,
            gross_return=gross_return,
            total_trades=trades,
            avg_position_size=1.0,
            max_concurrent_positions=1,
            regime_metrics={
                "ALL": {
                    "sharpe": float(pooled["sharpe_ratio"]),
                    "win_rate": float(pooled["win_rate_pct"]) / 100.0,
                    "profit_factor": profit_factor,
                    "trades": trades,
                    "max_drawdown_pct": float(pooled["max_drawdown_pct"]),
                }
            },
        )
        recorded += 1
        results.append(
            {
                "strategy_id": strategy_id,
                "symbol": symbol_label,
                "trades": trades,
                "status": "recorded",
                "reason": f"PF {profit_factor:.2f}, breakeven {evidence.breakeven_bps:.2f} bps",
            }
        )

    _print_report(results, recorded, args.dry_run)
    return 0


async def _latest_bar_end(symbol: str) -> str:
    async with get_session(read_only=True) as session:
        stmt = (
            select(PriceOHLCV.timestamp)
            .where(PriceOHLCV.symbol == symbol)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return str(row)[:10]


def _print_report(results: list[dict[str, Any]], recorded: int, dry_run: bool) -> None:
    print("=" * 78)
    print("STRATEGY EVIDENCE BOOTSTRAP" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 78)
    for item in results:
        print(
            f"  {item['status']:<13} {item['strategy_id']:<34} "
            f"{str(item.get('symbol', '-')):<9} {item.get('reason', '')}"
        )
    print()
    eligible = sum(1 for r in results if r["status"] == "recorded")
    print(f"strategies evaluated : {len(results)}")
    print(f"evidence recorded    : {recorded}")
    print(f"left without evidence: {len(results) - recorded} (stay experimental)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the strategy evidence store.")
    parser.add_argument("--lookback", type=int, default=1200, help="H1 candles per strategy")
    parser.add_argument("--min-trades", type=int, default=20, help="minimum closed trades to record")
    parser.add_argument("--include-synthesized", type=int, default=0, help="also evaluate N synthesized alphas")
    parser.add_argument(
        "--single-symbol",
        action="store_true",
        help="evaluate only the first applicable symbol instead of pooling all of them",
    )
    parser.add_argument("--dry-run", action="store_true", help="evaluate without writing the evidence store")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
