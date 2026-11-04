# ==============================================================================
# File: core/analytics/paper_analytics.py
# ==============================================================================

"""
Statistical Aggregation & Equity Curve Simulation for Paper Trading.
Pure calculation and grouping algorithms decoupled from database models.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from monika.core.primitives.constants import MARKET_OUTCOME_EXIT_REASONS

logger = logging.getLogger("TradingAgent.PaperTracker")


def _group_by_symbol(history):
    by_sym = {}
    from monika.core.primitives.constants import MARKET_OUTCOME_EXIT_REASONS

    for t in history:
        sym = t.get("symbol")
        if not sym:
            continue
        if sym not in by_sym:
            by_sym[sym] = {
                "trades": 0,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
                "_win_pnls": [],
                "_loss_pnls": [],
            }

        # Only count trades for win_rate if they are market exits
        if t.get("exit_reason") in MARKET_OUTCOME_EXIT_REASONS:
            by_sym[sym]["trades"] += 1
            by_sym[sym]["total"] += 1
            if t.get("exit_reason") == "tp_hit" or (t.get("pnl_pct") or 0) > 0:
                by_sym[sym]["wins"] += 1
            else:
                by_sym[sym]["losses"] += 1

        pnl = t.get("pnl_pct", 0) or 0.0
        if pnl > 0:
            by_sym[sym]["_win_pnls"].append(float(pnl))
        elif pnl < 0:
            by_sym[sym]["_loss_pnls"].append(abs(float(pnl)))

        by_sym[sym]["pnl_pct"] = round(by_sym[sym]["pnl_pct"] + pnl, 4)
        by_sym[sym]["total_pnl_pct"] = by_sym[sym]["pnl_pct"]
        by_sym[sym]["win_rate"] = (
            round(by_sym[sym]["wins"] / by_sym[sym]["trades"] * 100, 1) if by_sym[sym]["trades"] > 0 else 0.0
        )

    for s_data in by_sym.values():
        win_list = s_data.pop("_win_pnls", [])
        loss_list = s_data.pop("_loss_pnls", [])
        avg_w = sum(win_list) / len(win_list) if win_list else 0.0
        avg_l = sum(loss_list) / len(loss_list) if loss_list else 0.0
        payoff = round(avg_w / avg_l, 2) if avg_l > 0 else (round(avg_w, 2) if avg_w > 0 else 1.0)
        s_data["avg_win_pct"] = round(avg_w, 4)
        s_data["avg_loss_pct"] = round(avg_l, 4)
        s_data["payoff_ratio"] = payoff

    return by_sym


def _group_by_symbol_direction(history):
    by_sym_dir = {}
    from monika.core.primitives.constants import MARKET_OUTCOME_EXIT_REASONS

    for t in history:
        sym = t.get("symbol")
        direction = t.get("direction")
        if not sym or not direction:
            continue
        key = f"{sym}_{str(direction).lower()}"
        if key not in by_sym_dir:
            by_sym_dir[key] = {
                "trades": 0,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
            }

        if t.get("exit_reason") in MARKET_OUTCOME_EXIT_REASONS:
            by_sym_dir[key]["trades"] += 1
            by_sym_dir[key]["total"] += 1
            if t.get("exit_reason") == "tp_hit" or (t.get("pnl_pct") or 0) > 0:
                by_sym_dir[key]["wins"] += 1
            else:
                by_sym_dir[key]["losses"] += 1

        pnl = t.get("pnl_pct", 0) or 0.0
        by_sym_dir[key]["pnl_pct"] = round(by_sym_dir[key]["pnl_pct"] + pnl, 4)
        by_sym_dir[key]["total_pnl_pct"] = by_sym_dir[key]["pnl_pct"]
        by_sym_dir[key]["win_rate"] = (
            round(by_sym_dir[key]["wins"] / by_sym_dir[key]["trades"] * 100, 1)
            if by_sym_dir[key]["trades"] > 0
            else 0.0
        )
    return by_sym_dir


def aggregate_trade_statistics(results: Sequence[Any]) -> dict[str, Any]:
    """Aggregate win-rate, profit-factor, Sharpe, and breakdown metrics from closed trade records."""
    if not results:
        return {
            "total_trades": 0,
            "market_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_market_pct": 0.0,
            "win_rate_operational_pct": 0.0,
            "win_rate_pct": 0.0,
            "avg_pnl_pct": 0.0,
            "total_pnl_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "avg_rr_achieved": 0.0,
            "expectancy_per_trade_pct": 0.0,
            "expectancy_per_trade_R": 0.0,
            "has_positive_edge": False,
            "edge_alert": False,
            "by_confluence": {},
            "by_priced_in": {},
            "session_buckets": {
                "tokyo_00_08": {"label": "Tokyo (00:00-08:00 UTC)", "wins": 0, "total": 0},
                "london_08_13": {"label": "London Pre-Overlap (08:00-13:00 UTC)", "wins": 0, "total": 0},
                "overlap_13_16": {"label": "NY-London Overlap (13:00-16:00 UTC)", "wins": 0, "total": 0},
                "ny_16_21": {"label": "NY Post-London (16:00-21:00 UTC)", "wins": 0, "total": 0},
                "offpeak_21_00": {"label": "Off-Peak (21:00-00:00 UTC)", "wins": 0, "total": 0},
            },
            "avg_win_hold_hours": 0.0,
            "avg_loss_hold_hours": 0.0,
            "by_symbol": {},
            "by_symbol_direction": {},
            "recent_20": [],
        }

    records = [r for r, a in results]

    win_records = [r for r in records if (r.pnl_pct or 0) > 0 or r.exit_reason == "tp_hit"]
    loss_records = [r for r in records if (r.pnl_pct or 0) < 0 or r.exit_reason == "sl_hit"]
    pnl_values = [r.pnl_pct or 0 for r in records]

    market_records = [r for r in records if r.exit_reason in MARKET_OUTCOME_EXIT_REASONS]
    market_wins = [r for r in market_records if (r.pnl_pct or 0) > 0 or r.exit_reason == "tp_hit"]

    avg_win_pct = sum(r.pnl_pct or 0 for r in win_records) / len(win_records) if win_records else 0.0
    avg_loss_pct = abs(sum(r.pnl_pct or 0 for r in loss_records) / len(loss_records)) if loss_records else 0.0

    market_total = len(market_records)
    win_rate_market = len(market_wins) / market_total if market_total > 0 else 0.0
    loss_rate_market = 1.0 - win_rate_market if market_total > 0 else 0.0

    win_rate_operational = len(win_records) / len(records) if records else 0.0

    # Expectancy per trade
    expectancy = (win_rate_market * avg_win_pct) - (loss_rate_market * avg_loss_pct)
    avg_rr = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 0.0
    expectancy_r = (win_rate_market * avg_rr) - loss_rate_market

    # Compute extended metrics (Confluence, Priced In, Sessions, Durations)
    by_confluence: dict[str, dict[str, int]] = {}
    by_priced_in: dict[str, dict[str, Any]] = {}
    session_buckets = {
        "tokyo_00_08": {"label": "Tokyo (00:00-08:00 UTC)", "wins": 0, "total": 0},
        "london_08_13": {"label": "London Pre-Overlap (08:00-13:00 UTC)", "wins": 0, "total": 0},
        "overlap_13_16": {"label": "NY-London Overlap (13:00-16:00 UTC)", "wins": 0, "total": 0},
        "ny_16_21": {"label": "NY Post-London (16:00-21:00 UTC)", "wins": 0, "total": 0},
        "offpeak_21_00": {"label": "Off-Peak (21:00-00:00 UTC)", "wins": 0, "total": 0},
    }

    win_durations = []
    loss_durations = []

    for r, a in results:
        is_win = (r.pnl_pct or 0) > 0

        # Confluence
        if a and a.confluence_score is not None:
            cs = a.confluence_score
            cb = f"{cs}"
            if cb not in by_confluence:
                by_confluence[cb] = {"wins": 0, "total": 0}
            by_confluence[cb]["total"] += 1
            if is_win:
                by_confluence[cb]["wins"] += 1

        # Priced In
        if a and a.priced_in_score is not None:
            ps = a.priced_in_score
            pb = f"pi_{ps}"
            if pb not in by_priced_in:
                by_priced_in[pb] = {"score": ps, "wins": 0, "total": 0}
            by_priced_in[pb]["total"] += 1
            if is_win:
                by_priced_in[pb]["wins"] += 1

        # Market Session Bucketing (based on open hour UTC)
        if r.opened_at:
            hr = r.opened_at.hour
            if 0 <= hr < 8:
                sb_key = "tokyo_00_08"
            elif 8 <= hr < 13:
                sb_key = "london_08_13"
            elif 13 <= hr < 16:
                sb_key = "overlap_13_16"
            elif 16 <= hr < 21:
                sb_key = "ny_16_21"
            else:
                sb_key = "offpeak_21_00"

            session_buckets[sb_key]["total"] += 1
            if is_win:
                session_buckets[sb_key]["wins"] += 1

        # Trade Durations
        if r.opened_at and r.closed_at:
            duration_hours = (r.closed_at - r.opened_at).total_seconds() / 3600.0
            if is_win:
                win_durations.append(duration_hours)
            else:
                loss_durations.append(duration_hours)

    avg_win_hold = sum(win_durations) / len(win_durations) if win_durations else 0.0
    avg_loss_hold = sum(loss_durations) / len(loss_durations) if loss_durations else 0.0

    history = [
        {
            "symbol": r.symbol,
            "direction": r.direction,
            "exit_reason": r.exit_reason,
            "pnl_pct": r.pnl_pct or 0.0,
        }
        for r in records
    ]

    return {
        "total_trades": len(records),
        "market_trades": market_total,
        "wins": len(win_records),
        "losses": len(loss_records),
        "win_rate_market_pct": round(win_rate_market * 100, 1),
        "win_rate_operational_pct": round(win_rate_operational * 100, 1),
        "win_rate_pct": round(win_rate_market * 100, 1),
        "avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 2) if pnl_values else 0.0,
        "total_pnl_pct": round(sum(pnl_values), 2),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "avg_rr_achieved": round(avg_rr, 2),
        "expectancy_per_trade_pct": round(expectancy, 2),
        "expectancy_per_trade_R": round(expectancy_r, 2),
        "has_positive_edge": expectancy > 0,
        "edge_alert": expectancy < 0,
        "by_confluence": by_confluence,
        "by_priced_in": by_priced_in,
        "session_buckets": session_buckets,
        "avg_win_hold_hours": round(avg_win_hold, 1),
        "avg_loss_hold_hours": round(avg_loss_hold, 1),
        "by_symbol": _group_by_symbol(history),
        "by_symbol_direction": _group_by_symbol_direction(history),
        "recent_20": [
            {"symbol": h["symbol"], "exit_reason": h["exit_reason"], "pnl_pct": h["pnl_pct"]} for h in history[-20:]
        ],
    }


def calculate_equity_curve(records: Sequence[Any], starting_equity: float = 10000.0) -> dict[str, Any]:
    """Simulate equity curve, peak equity, and maximum drawdown percentage."""
    if not records:
        return {}

    equity = starting_equity
    peak_equity = starting_equity
    max_drawdown = 0.0
    equity_history = [{"date": records[0].opened_at.isoformat() if records[0].opened_at else None, "equity": equity}]

    for record in records:
        if record.pnl_pct is not None:
            trade_pnl = equity * (record.pnl_pct / 100.0)
        else:
            trade_pnl = 0.0

        equity += trade_pnl
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)

        equity_history.append(
            {
                "date": record.closed_at.isoformat() if record.closed_at else None,
                "equity": round(equity, 2),
                "trade_pnl": round(trade_pnl, 2),
                "symbol": record.symbol,
                "direction": record.direction,
            }
        )

    return {
        "starting_equity": starting_equity,
        "final_equity": round(equity, 2),
        "total_return_pct": round((equity - starting_equity) / starting_equity * 100, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "equity_history": equity_history[-50:],
    }
