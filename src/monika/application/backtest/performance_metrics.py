"""Canonical per-trade performance statistics.

The repository used three different definitions of "Sharpe ratio":

* the report generator resamples the equity curve to daily returns and
  annualises with ``sqrt(252)`` — the industry standard;
* the isolated strategy harness multiplied a per-trade ratio by
  ``sqrt(252 * 24 / mean_bars_held)``;
* the empirical playbook builder multiplied a per-trade ratio by
  ``sqrt(min(252, trade_count))``.

The last two are not annualised Sharpe ratios. Multiplying by ``sqrt(n)``
yields the *t-statistic* of the mean trade, and a t-statistic labelled as a
Sharpe ratio produces values such as 10.4, which no real strategy can have.

This module provides one definition that every caller shares:

* ``per_trade_sharpe`` - mean trade return divided by its standard deviation;
* ``annualized_sharpe`` - the per-trade ratio annualised with the *observed*
  trade frequency of the measurement window;
* ``t_statistic`` - the significance of the mean trade, kept separate so it
  can never be mistaken for an annualised ratio;
* ``is_reliable`` - false when the sample or the window is too small to
  support an annualised number.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

TRADING_DAYS_PER_YEAR = 252.0
DAYS_PER_YEAR = 365.25

MIN_TRADES_FOR_RELIABILITY = 30
MIN_WINDOW_DAYS_FOR_RELIABILITY = 90.0
# Two-sided 5% significance of the mean trade. Below this a positive profit
# factor is not separable from luck, so it must not become promotion evidence.
MIN_T_STATISTIC_FOR_EVIDENCE = 2.0


def _std(returns: Sequence[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(variance)


def compute_trade_statistics(
    returns: Iterable[float],
    window_days: float | None = None,
) -> dict[str, Any]:
    """Compute the canonical statistics of a sequence of per-trade returns.

    ``returns`` are per-trade equity fractions (for example 0.01 for a full
    1% risk trade). ``window_days`` is the length of the measurement window in
    calendar days; without it no annualised ratio can be derived.
    """
    values = [float(r) for r in returns]
    n = len(values)
    if n == 0:
        return {
            "trades": 0,
            "mean_return": 0.0,
            "std_return": 0.0,
            "per_trade_sharpe": 0.0,
            "annualized_sharpe": None,
            "t_statistic": 0.0,
            "trades_per_year": None,
            "window_days": window_days,
            "is_reliable": False,
        }

    mean = sum(values) / n
    std = _std(values)
    per_trade_sharpe = (mean / std) if std > 1e-12 else 0.0
    t_statistic = per_trade_sharpe * math.sqrt(n)

    trades_per_year: float | None = None
    annualized_sharpe: float | None = None
    if window_days and window_days > 0:
        years = window_days / DAYS_PER_YEAR
        if years > 0:
            trades_per_year = n / years
            annualized_sharpe = per_trade_sharpe * math.sqrt(trades_per_year)

    reliable = (
        n >= MIN_TRADES_FOR_RELIABILITY
        and bool(window_days)
        and float(window_days or 0.0) >= MIN_WINDOW_DAYS_FOR_RELIABILITY
        and std > 1e-12
    )

    return {
        "trades": n,
        "mean_return": mean,
        "std_return": std,
        "per_trade_sharpe": per_trade_sharpe,
        "annualized_sharpe": round(annualized_sharpe, 2) if annualized_sharpe is not None else None,
        "t_statistic": round(t_statistic, 2),
        "trades_per_year": round(trades_per_year, 2) if trades_per_year is not None else None,
        "window_days": round(float(window_days), 1) if window_days else None,
        "is_reliable": bool(reliable),
    }


def window_days_from_trades(trades: Sequence[Any]) -> float | None:
    """Length of the measurement window in days from trade entry/exit times."""
    times: list[Any] = []
    for trade in trades:
        entry = getattr(trade, "entry_time", None)
        exit_time = getattr(trade, "exit_time", None)
        if entry is None and isinstance(trade, dict):
            entry = trade.get("entry_time")
            exit_time = trade.get("exit_time")
        if entry is not None:
            times.append(entry)
        if exit_time is not None:
            times.append(exit_time)
    if len(times) < 2:
        return None
    try:
        span = max(times) - min(times)
    except TypeError:
        return None
    return span.total_seconds() / 86400.0


__all__ = [
    "DAYS_PER_YEAR",
    "MIN_TRADES_FOR_RELIABILITY",
    "MIN_T_STATISTIC_FOR_EVIDENCE",
    "MIN_WINDOW_DAYS_FOR_RELIABILITY",
    "TRADING_DAYS_PER_YEAR",
    "compute_trade_statistics",
    "window_days_from_trades",
]
