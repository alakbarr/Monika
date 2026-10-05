"""
Safe Analytical Query Builder and Institutional Audit Handler.
Executes parameterized aggregations on historical trade performance,
regime expectancy, holding times, session win rates, MAE/MFE distributions, and slippage.
"""

from datetime import datetime, timezone, timedelta
import logging
import math
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Position, PaperTradeRecord, TradeOutcome, OrderLog, AssetAnalysis
from analysis.tools.registry import ToolRegistry, ToolDefinition
import utils.clock as clock

logger = logging.getLogger("TradingAgent.Tools.AnalyticalQuery")


def _get_session_and_symbol(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], Optional[str], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    if not sym:
        sym = args.get("symbol") or getattr(executor, "symbol", None)
    if sym and isinstance(sym, str):
        sym = sym.strip().upper().replace("/", "")
    return session, sym, settings


def _calculate_rr(entry: Optional[float], sl: Optional[float], tp: Optional[float]) -> float:
    if not entry or not sl or not tp:
        return 0.0
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk <= 1e-8:
        return 0.0
    return round(reward / risk, 2)


def _get_rr_bucket(rr: float) -> str:
    if rr < 1.5:
        return "< 1:1.5"
    elif rr < 2.0:
        return "1:1.5 - 1:2.0"
    elif rr < 2.5:
        return "1:2.0 - 1:2.5"
    else:
        return ">= 1:2.5"


async def handle_run_analytical_query(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not session:
        return {"status": "unavailable", "message": "Database session required for analytical query"}

    metric = args.get("metric", "overview").lower()
    group_by = args.get("group_by", "none").lower()
    days_back = int(args.get("days_back", 90))
    min_rr = float(args.get("min_rr", 0.0))
    cutoff = clock.now() - timedelta(days=days_back)

    # 1. Fetch Closed Trade Outcomes and Paper Trade Records
    outcomes_stmt = select(TradeOutcome).where(
        or_filter := and_(
            TradeOutcome.closed_at.is_not(None),
            TradeOutcome.closed_at >= cutoff
        )
    )
    if symbol:
        outcomes_stmt = outcomes_stmt.where(TradeOutcome.symbol == symbol)

    outcomes = (await session.execute(outcomes_stmt)).scalars().all()

    # Also query positions if TradeOutcome is empty / sparse
    positions_stmt = select(Position).where(
        and_(
            Position.status == "closed",
            Position.closed_at.is_not(None),
            Position.closed_at >= cutoff
        )
    )
    if symbol:
        positions_stmt = positions_stmt.where(Position.symbol == symbol)
    positions = (await session.execute(positions_stmt)).scalars().all()

    # Rejection query handler if requested
    if metric == "rejection_summary":
        log_stmt = select(OrderLog).where(OrderLog.timestamp >= cutoff)
        if symbol:
            log_stmt = log_stmt.where(OrderLog.symbol == symbol)
        logs = (await session.execute(log_stmt.order_by(OrderLog.timestamp.desc()))).scalars().all()

        rejections_by_reason: Dict[str, int] = {}
        total_evaluations = len(logs)
        total_rejections = 0
        for log in logs:
            res_str = str(log.result or "").lower()
            if "reject" in res_str or "block" in res_str or "fail" in res_str:
                total_rejections += 1
                reason = "Unknown / RiskGate Filter"
                for keyword in ["drawdown", "news", "spread", "correlation", "max position", "balance", "margin", "confluence", "stale"]:
                    if keyword in res_str:
                        reason = f"{keyword.capitalize()} Filter"
                        break
                rejections_by_reason[reason] = rejections_by_reason.get(reason, 0) + 1

        return {
            "metric": "rejection_summary",
            "lookback_days": days_back,
            "symbol": symbol or "ALL",
            "total_evaluations": total_evaluations,
            "total_rejections": total_rejections,
            "rejection_rate_pct": round((total_rejections / max(1, total_evaluations)) * 100, 2),
            "breakdown": rejections_by_reason
        }

    # Normalize trades list
    trades: List[Dict[str, Any]] = []
    for o in outcomes:
        pnl = float(o.pnl_usd or 0.0)
        rr = _calculate_rr(o.entry_price, o.stop_loss, o.take_profit)
        if min_rr > 0 and rr < min_rr:
            continue
        hour_val = "Unknown"
        if o.closed_at:
            try:
                dt_c = o.closed_at if isinstance(o.closed_at, datetime) else datetime.fromisoformat(str(o.closed_at))
                if dt_c.tzinfo is None:
                    dt_c = dt_c.replace(tzinfo=timezone.utc)
                hour_val = f"{dt_c.astimezone(timezone(timedelta(hours=7))).hour:02d}:00 WIB"
            except Exception:
                pass
        trades.append({
            "id": o.id,
            "symbol": o.symbol,
            "direction": o.direction,
            "pnl": pnl,
            "is_win": pnl > 0,
            "rr": rr,
            "rr_bucket": _get_rr_bucket(rr),
            "holding_hours": float(o.holding_hours or 0.0),
            "mae_pips": float(o.mae_pips or 0.0),
            "mfe_pips": float(o.mfe_pips or 0.0),
            "sl_slippage_pips": float(o.sl_slippage_pips or 0.0),
            "session": str(o.entry_session or "Unknown"),
            "market_regime": str(o.market_regime or "Unknown"),
            "decision_source": str(o.decision_source or "LLM_Agent"),
            "closed_at": o.closed_at.isoformat() if o.closed_at else "",
            "hour": hour_val,
            "hour_wib": hour_val,
        })

    # If no TradeOutcome records, fallback to closed positions
    if not trades and positions:
        for p in positions:
            pnl = float(p.pnl or 0.0)
            rr = _calculate_rr(p.entry_price, p.sl, p.tp)
            if min_rr > 0 and rr < min_rr:
                continue
            holding_h = 0.0
            if p.opened_at and p.closed_at:
                holding_h = round((p.closed_at - p.opened_at).total_seconds() / 3600, 2)
            hour_val = "Unknown"
            if p.closed_at:
                try:
                    dt_c = p.closed_at if isinstance(p.closed_at, datetime) else datetime.fromisoformat(str(p.closed_at))
                    if dt_c.tzinfo is None:
                        dt_c = dt_c.replace(tzinfo=timezone.utc)
                    hour_val = f"{dt_c.astimezone(timezone(timedelta(hours=7))).hour:02d}:00 WIB"
                except Exception:
                    pass
            trades.append({
                "id": p.id,
                "symbol": p.symbol,
                "direction": p.direction,
                "pnl": pnl,
                "is_win": pnl > 0,
                "rr": rr,
                "rr_bucket": _get_rr_bucket(rr),
                "holding_hours": holding_h,
                "mae_pips": float(p.mae_pips or 0.0),
                "mfe_pips": float(p.mfe_pips or 0.0),
                "sl_slippage_pips": float(p.sl_slippage_pips or 0.0),
                "session": str(p.entry_session or "Unknown"),
                "market_regime": str(p.market_regime or "Unknown"),
                "decision_source": "MT5_Position",
                "closed_at": p.closed_at.isoformat() if p.closed_at else "",
                "hour": hour_val,
                "hour_wib": hour_val,
            })

    if not trades:
        return {
            "metric": metric,
            "lookback_days": days_back,
            "symbol": symbol or "ALL",
            "total_trades": 0,
            "message": "No closed trades found matching criteria."
        }

    def _compute_metrics_for_subset(sub_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        count = len(sub_trades)
        if count == 0:
            return {"count": 0}

        wins = [t for t in sub_trades if t["is_win"]]
        losses = [t for t in sub_trades if not t["is_win"]]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round((win_count / count) * 100, 2)

        win_rrs = [t["rr"] for t in wins if t.get("rr") and t["rr"] > 0]
        loss_rrs = [t["rr"] for t in losses if t.get("rr") and t["rr"] > 0]
        avg_win_rr = round(float(np.mean(win_rrs)), 2) if win_rrs else 0.0
        avg_loss_rr = round(float(np.mean(loss_rrs)), 2) if loss_rrs else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        net_pnl = round(gross_profit - gross_loss, 2)
        profit_factor = round(gross_profit / max(1e-6, gross_loss), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 1.0)

        avg_win = (gross_profit / win_count) if win_count > 0 else 0.0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0.0
        expectancy_usd = round(((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss), 2)

        pnl_arr = np.array([t["pnl"] for t in sub_trades], dtype=float)
        std_pnl = float(np.std(pnl_arr)) if len(pnl_arr) > 1 else 1.0
        mean_pnl = float(np.mean(pnl_arr))
        sharpe_ratio = round(mean_pnl / max(1e-6, std_pnl) * math.sqrt(252), 2) if std_pnl > 0 else 0.0

        avg_holding_win = round(sum(t["holding_hours"] for t in wins) / max(1, win_count), 2)
        avg_holding_loss = round(sum(t["holding_hours"] for t in losses) / max(1, loss_count), 2)

        mae_vals = [t["mae_pips"] for t in sub_trades if t["mae_pips"] > 0]
        mfe_vals = [t["mfe_pips"] for t in sub_trades if t["mfe_pips"] > 0]
        avg_mae = round(float(np.mean(mae_vals)), 2) if mae_vals else 0.0
        avg_mfe = round(float(np.mean(mfe_vals)), 2) if mfe_vals else 0.0

        slippage_vals = [t["sl_slippage_pips"] for t in sub_trades if t["sl_slippage_pips"] > 0]
        avg_slippage = round(float(np.mean(slippage_vals)), 2) if slippage_vals else 0.0
        max_slippage = round(float(np.max(slippage_vals)), 2) if slippage_vals else 0.0

        return {
            "total_trades": count,
            "won": win_count,
            "lost": loss_count,
            "win_rate_pct": win_rate,
            "net_pnl_usd": net_pnl,
            "profit_factor": profit_factor,
            "expectancy_usd_per_trade": expectancy_usd,
            "sharpe_ratio": sharpe_ratio,
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "avg_win_rr": avg_win_rr,
            "avg_loss_rr": avg_loss_rr,
            "avg_holding_win_hours": avg_holding_win,
            "avg_holding_loss_hours": avg_holding_loss,
            "avg_mae_pips": avg_mae,
            "avg_mfe_pips": avg_mfe,
            "avg_sl_slippage_pips": avg_slippage,
            "max_sl_slippage_pips": max_slippage,
        }

    if group_by == "none" or group_by not in ["session", "market_regime", "symbol", "decision_source", "risk_reward_bucket", "hour", "hour_wib", "hour_utc"]:
        result = _compute_metrics_for_subset(trades)
        result["metric"] = metric
        result["lookback_days"] = days_back
        result["symbol"] = symbol or "ALL"
        result["min_rr_filter"] = min_rr
        return result

    # Grouped analysis
    grouped_trades: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        g_key = t.get(group_by, "Unknown")
        if not g_key or g_key == "None":
            g_key = "Unknown"
        grouped_trades.setdefault(str(g_key), []).append(t)

    grouped_results: Dict[str, Any] = {}
    for g_key, group_list in grouped_trades.items():
        grouped_results[g_key] = _compute_metrics_for_subset(group_list)

    return {
        "metric": metric,
        "group_by": group_by,
        "lookback_days": days_back,
        "symbol": symbol or "ALL",
        "min_rr_filter": min_rr,
        "overall": _compute_metrics_for_subset(trades),
        "breakdown": grouped_results
    }


def register_analytical_query_tool():
    registry = ToolRegistry.get_instance()
    tool = ToolDefinition(
        name="run_analytical_query",
        description="Execute safe, parameterized analytical aggregation query on historical trade performance.",
        parameters={
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": ["win_rate", "profit_factor", "sharpe_ratio", "expectancy_usd", "mae_mfe_distribution", "holding_time", "rejection_summary", "slippage_summary", "overview"]},
                "group_by": {"type": "string", "enum": ["session", "market_regime", "symbol", "decision_source", "risk_reward_bucket", "none"]},
                "days_back": {"type": "integer"},
                "symbol": {"type": "string"},
                "min_rr": {"type": "number"}
            },
            "required": ["metric"]
        },
        handler=handle_run_analytical_query,
        toolset="analytics",
        requires_db=True,
    )
    registry.register(tool)


register_analytical_query_tool()
