"""
Alpha validation metrics for post-backtest and walk-forward validation.
Tests if observed strategy returns are genuine market-neutral alpha or beta riding.

Implements:
1. Directional Imbalance check (<85% trades in single direction).
2. Half-Consistency test (Sortino > 0 in both first half and second half of sample).
3. Cost Stress Test (remains profitable under 2x execution/spread/commission costs).
"""
import math
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence


@dataclass
class AlphaValidation:
    passed: bool
    directional_ok: bool
    half_consistent: bool
    cost_stress_ok: bool
    max_direction_pct: float
    h1_sortino: float
    h2_sortino: float
    stress_pnl: float
    details: str


def _calculate_sortino(returns: Sequence[float]) -> float:
    """Calculate Sortino ratio from return sequence."""
    if not returns or len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0.0]

    if not downside:
        # If zero negative returns, Sortino is positive and high
        return 10.0 if mean_ret > 0 else 0.0

    downside_var = sum(r * r for r in downside) / len(returns)
    downside_dev = math.sqrt(downside_var)

    if downside_dev < 1e-12:
        return 10.0 if mean_ret > 0 else 0.0

    return float(mean_ret / downside_dev)


def validate_alpha(
    trades: List[Any],
    equity_curve: Optional[List[float]] = None,
    cost_multiplier: float = 2.0,
    max_directional_threshold: float = 0.85,
    initial_equity: float = 10000.0,
) -> AlphaValidation:
    """
    Validate trade sequence against directional bias, split-sample consistency, and fee stress.

    Args:
        trades: List of trade objects (BacktestTrade) or dictionaries.
        equity_curve: Optional timeline of account equity values.
        cost_multiplier: Stress test multiplier for commission and slippage friction (default 2.0x).
        max_directional_threshold: Maximum allowed fraction of unidirectional trades (default 0.85).
        initial_equity: Initial account equity in dollars for converting percentage PnL (default 10000.0).
    """
    if not trades:
        return AlphaValidation(
            passed=False,
            directional_ok=False,
            half_consistent=False,
            cost_stress_ok=False,
            max_direction_pct=0.0,
            h1_sortino=0.0,
            h2_sortino=0.0,
            stress_pnl=0.0,
            details="No trades to evaluate.",
        )

    # 1. Directional Imbalance Check
    directions = []
    for t in trades:
        d = getattr(t, "direction", None)
        if d is None and isinstance(t, dict):
            d = t.get("direction")
        if d:
            directions.append(str(d).upper())

    if directions:
        buy_count = sum(1 for d in directions if "BUY" in d or "LONG" in d)
        sell_count = sum(1 for d in directions if "SELL" in d or "SHORT" in d)
        max_dir_count = max(buy_count, sell_count)
        max_dir_pct = round(max_dir_count / len(directions), 3)
        directional_ok = max_dir_pct <= max_directional_threshold
    else:
        max_dir_pct = 0.5
        directional_ok = True

    # 2. Half-Consistency Test (Sortino H1 > 0 and Sortino H2 > 0)
    pnls = []
    for t in trades:
        pnl = getattr(t, "pnl_pct", None)
        if pnl is None and hasattr(t, "pnl"):
            pnl = getattr(t, "pnl", None)
        if pnl is None and isinstance(t, dict):
            pnl = t.get("pnl_pct", t.get("pnl", 0.0))
        pnls.append(float(pnl or 0.0))

    if equity_curve and len(equity_curve) >= 6:
        # Use equity curve return series (supports list of floats or list of dicts)
        eq_floats: List[float] = [
            float(p.get("equity", p.get("value", 0.0))) if isinstance(p, dict) else float(p)
            for p in equity_curve
        ]
        rets = [eq_floats[i] - eq_floats[i - 1] for i in range(1, len(eq_floats))]
    else:
        rets = pnls

    if len(rets) >= 4:
        mid = len(rets) // 2
        h1 = rets[:mid]
        h2 = rets[mid:]
        h1_sortino = round(_calculate_sortino(h1), 3)
        h2_sortino = round(_calculate_sortino(h2), 3)
        half_consistent = bool(h1_sortino > 0.0 and h2_sortino > 0.0)
    else:
        h1_sortino = round(_calculate_sortino(rets), 3)
        h2_sortino = h1_sortino
        half_consistent = bool(h1_sortino > 0.0)

    # 3. Cost Stress Test (Profitable under 2.0x friction)
    stress_pnls = []
    for t in trades:
        base_pnl = getattr(t, "pnl_pct", None)
        if base_pnl is None and hasattr(t, "pnl"):
            base_pnl = getattr(t, "pnl", None)
        if base_pnl is None and isinstance(t, dict):
            base_pnl = t.get("pnl_pct", t.get("pnl", 0.0))
        base_pnl = float(base_pnl or 0.0)

        # Estimate cost or commission
        comm = getattr(t, "commission", None)
        if comm is None and isinstance(t, dict):
            comm = t.get("commission", 0.0)
        if comm is None:
            # Fallback estimation for BacktestTrade without commission column
            lots = float(getattr(t, "executed_lots", getattr(t, "lots", 0.1)) or 0.1)
            comm = getattr(t, "friction_usd", None) or (5.0 * lots)
        comm = abs(float(comm or 0.0))

        # Extra cost penalty under multiplier
        extra_cost = comm * (cost_multiplier - 1.0)
        base_pnl_usd = (float(base_pnl or 0.0) / 100.0) * initial_equity
        stress_pnls.append(base_pnl_usd - extra_cost)

    stress_total = round(sum(stress_pnls), 4)
    cost_stress_ok = bool(stress_total > 0.0)

    passed = bool(directional_ok and half_consistent and cost_stress_ok)

    details = (
        f"Directional={max_dir_pct:.1%} ({'PASS' if directional_ok else 'FAIL'}), "
        f"HalfConsistency=[H1={h1_sortino}, H2={h2_sortino}] ({'PASS' if half_consistent else 'FAIL'}), "
        f"CostStress2x=${stress_total:.2f} ({'PASS' if cost_stress_ok else 'FAIL'})"
    )

    return AlphaValidation(
        passed=passed,
        directional_ok=directional_ok,
        half_consistent=half_consistent,
        cost_stress_ok=cost_stress_ok,
        max_direction_pct=max_dir_pct,
        h1_sortino=h1_sortino,
        h2_sortino=h2_sortino,
        stress_pnl=stress_total,
        details=details,
    )
