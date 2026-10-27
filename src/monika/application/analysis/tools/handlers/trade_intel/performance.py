# ==============================================================================
# File: analysis/tools/handlers/trade_intel/performance.py
# ==============================================================================

"""
Trade history, PnL summary, and portfolio exposure tool handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.base_handler import ToolHandler
from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry, register_tool
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    DecisionReflection,
    PaperTradeRecord,
    TelegramConversation,
    TradeTrigger,
)
from monika.application.analysis.tools.handlers.trade_intel.base import _get_session_and_settings, logger


async def handle_get_trade_history(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    effective_session = session or getattr(executor, "session", None)
    try:
        limit = max(1, min(int(args.get("limit", 10)), 100))
    except ValueError, TypeError:
        limit = 10

    status_filter = args.get("status")
    symbol = args.get("symbol")
    days_back = args.get("days_back")

    if not effective_session:
        return {"trades": [], "count": 0, "status": "no_session"}

    query = select(PaperTradeRecord)
    if status_filter and status_filter.lower() != "all":
        query = query.where(PaperTradeRecord.status == status_filter.lower())
    if symbol:
        clean_sym = symbol.strip().upper().replace("/", "")
        query = query.where(PaperTradeRecord.symbol == clean_sym)
    if days_back is not None:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=float(days_back))
            query = query.where(PaperTradeRecord.opened_at >= cutoff)
        except ValueError, TypeError:
            pass
    query = query.order_by(desc(PaperTradeRecord.opened_at)).limit(limit)

    rows = (await effective_session.execute(query)).scalars().all()
    trades = [
        {
            "id": r.id,
            "ticket": getattr(r, "mt5_ticket", f"PAPER-{r.id}"),
            "symbol": r.symbol,
            "direction": r.direction,
            "entry_price": r.entry_price,
            "stop_loss": r.stop_loss,
            "take_profit": r.take_profit,
            "lot_size": getattr(r, "lot_size", getattr(r, "volume", 0.01)),
            "status": r.status,
            "pnl_usd": getattr(r, "pnl_usd", None),
            "pnl_pct": r.pnl_pct,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "mode": "paper",
        }
        for r in rows
    ]

    # Query live Position records if requested or if paper trades list is empty
    mode = str(args.get("mode") or "").lower()
    if mode in ("live", "all") or not trades:
        from monika.infrastructure.database.models import Position

        pos_q = select(Position)
        if status_filter and status_filter.lower() != "all":
            pos_q = pos_q.where(Position.status == status_filter.lower())
        if symbol:
            clean_sym = symbol.strip().upper().replace("/", "")
            pos_q = pos_q.where(Position.symbol == clean_sym)
        if days_back is not None:
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=float(days_back))
                pos_q = pos_q.where(Position.opened_at >= cutoff)
            except ValueError, TypeError:
                pass
        pos_q = pos_q.order_by(desc(Position.opened_at)).limit(limit)
        pos_rows = (await effective_session.execute(pos_q)).scalars().all()
        for p in pos_rows:
            trades.append(
                {
                    "id": p.id,
                    "ticket": getattr(p, "mt5_ticket", p.id),
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "stop_loss": getattr(p, "sl", getattr(p, "stop_loss", None)),
                    "take_profit": getattr(p, "tp", getattr(p, "take_profit", None)),
                    "lot_size": getattr(p, "volume", 0.01),
                    "status": p.status,
                    "pnl_usd": getattr(p, "pnl", getattr(p, "unrealized_pnl", None)),
                    "pnl_pct": getattr(p, "pnl_pct", None),
                    "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                    "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                    "mode": "live",
                }
            )

    return {"count": len(trades), "trades": trades}


@register_tool("get_trade_history", aliases=["trade_history"], category="POSITION", parallel_safe=True)
class GetTradeHistoryHandler(ToolHandler):
    name = "get_trade_history"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_trade_history(args, session=session, executor=executor, **kwargs)


async def handle_get_trade_details(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    effective_session = session or getattr(executor, "session", None)
    trade_id = args.get("trade_id") or args.get("id") or args.get("ticket") or args.get("analysis_id")
    if not trade_id:
        recent = (
            (
                await effective_session.execute(select(PaperTradeRecord).order_by(PaperTradeRecord.id.desc()).limit(1))
            ).scalar_one_or_none()
            if effective_session
            else None
        )
        if recent:
            trade_id = recent.id
        else:
            return {"error": "Missing trade_id and no recorded trades available."}
    if not effective_session:
        return {"status": "no_session"}

    try:
        tid = int(trade_id)
    except ValueError, TypeError:
        return {"error": f"Invalid trade_id: {trade_id}"}

    record = (
        await effective_session.execute(select(PaperTradeRecord).where(PaperTradeRecord.id == tid))
    ).scalar_one_or_none()

    is_live = False
    if not record:
        from monika.infrastructure.database.models import Position

        record = (
            await effective_session.execute(select(Position).where((Position.id == tid) | (Position.mt5_ticket == tid)))
        ).scalar_one_or_none()
        if record:
            is_live = True

    if not record:
        return {"status": "not_found", "trade_id": tid}

    reflection_data = None
    analysis_id = getattr(record, "analysis_id", None)
    symbol = getattr(record, "symbol", "")
    try:
        conds = [DecisionReflection.symbol == symbol]
        if analysis_id is not None and str(analysis_id).isdigit():
            conds.append(DecisionReflection.analysis_id == int(analysis_id))
        ref_q = select(DecisionReflection).where(or_(*conds)).order_by(desc(DecisionReflection.created_at)).limit(1)
        ref_row = (await effective_session.execute(ref_q)).scalar_one_or_none()
        if ref_row:
            reflection_data = {
                "specific_lesson": ref_row.specific_lesson,
                "next_trade_adjustment": ref_row.next_trade_adjustment,
                "lesson_tags": ref_row.lesson_tags,
                "alpha_lesson": ref_row.alpha_lesson,
                "reflection_text": ref_row.reflection_text,
            }
    except Exception:
        pass

    debate_data = None
    try:
        if analysis_id:
            ana_row = (
                await effective_session.execute(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))
            ).scalar_one_or_none()
            if ana_row:
                debate_data = {
                    "debate_verdict": ana_row.debate_verdict,
                    "debate_reason": ana_row.debate_reason,
                    "debate_bull_thesis": ana_row.debate_bull_thesis,
                    "debate_bear_dissent": ana_row.debate_bear_dissent,
                    "confluence_score": ana_row.confluence_score,
                    "confidence": ana_row.confidence,
                    "rationale": ana_row.rationale,
                }
    except Exception:
        pass

    entry_price = getattr(record, "entry_price", None) or getattr(record, "open_price", None)
    stop_loss = getattr(record, "stop_loss", None) or getattr(record, "sl", None)
    take_profit = getattr(record, "take_profit", None) or getattr(record, "tp", None)
    direction = getattr(record, "direction", None) or getattr(record, "order_type", None)

    return {
        "id": getattr(record, "ticket", None) or record.id,
        "mode": "live" if is_live else "paper",
        "symbol": record.symbol,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "exit_price": getattr(record, "exit_price", None) or getattr(record, "close_price", None),
        "exit_reason": getattr(record, "exit_reason", None),
        "status": getattr(record, "status", None),
        "pnl_usd": getattr(record, "pnl_usd", None) or getattr(record, "pnl", None),
        "pnl_pct": getattr(record, "pnl_pct", None),
        "opened_at": getattr(record, "opened_at").isoformat()
        if getattr(record, "opened_at", None) is not None and hasattr(getattr(record, "opened_at"), "isoformat")
        else None,
        "closed_at": getattr(record, "closed_at").isoformat()
        if getattr(record, "closed_at", None) is not None and hasattr(getattr(record, "closed_at"), "isoformat")
        else None,
        "reflection": reflection_data,
        "debate_analysis": debate_data,
    }


@register_tool("get_trade_details", aliases=["trade_details"], category="POSITION", parallel_safe=True)
class GetTradeDetailsHandler(ToolHandler):
    name = "get_trade_details"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_trade_details(args, session=session, executor=executor, **kwargs)


async def handle_get_paper_trading_performance(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"status": "no_session"}

    days_back = args.get("days_back") or args.get("days")
    if days_back is not None:
        try:
            days_back = int(days_back)
        except ValueError, TypeError:
            days_back = None
    symbol = args.get("symbol")
    mode = str(args.get("mode", "paper")).lower()

    if mode in ("live", "all"):
        from datetime import timedelta

        from monika.infrastructure.database.models import Position

        q = select(Position).where(Position.status == "closed")
        if mode == "live":
            q = q.where(Position.is_paper == False)
        if days_back:
            since = clock.now() - timedelta(days=days_back)
            q = q.where(Position.closed_at >= since)
        if symbol:
            q = q.where(Position.symbol == symbol.strip().upper().replace("/", ""))

        pos_records = list((await effective_session.execute(q)).scalars().all())
        if pos_records or mode == "live":
            wins = [p for p in pos_records if (p.pnl or 0) > 0]
            losses = [p for p in pos_records if (p.pnl or 0) <= 0]
            total_trades = len(pos_records)
            win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
            total_pnl = sum(p.pnl or 0 for p in pos_records)
            avg_win = (sum(p.pnl or 0 for p in wins) / len(wins)) if wins else 0.0
            avg_loss = (abs(sum(p.pnl or 0 for p in losses)) / len(losses)) if losses else 0.0
            gross_win = sum(p.pnl or 0 for p in wins)
            gross_loss = abs(sum(p.pnl or 0 for p in losses))
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

            return {
                "mode": mode,
                "total_trades": total_trades,
                "wins": len(wins),
                "losses": len(losses),
                "win_rate_pct": round(win_rate, 2),
                "total_pnl": round(total_pnl, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "profit_factor": round(profit_factor, 2),
                "recent_trades": [
                    {
                        "ticket": p.mt5_ticket,
                        "symbol": p.symbol,
                        "direction": p.direction,
                        "volume": p.volume,
                        "entry_price": p.entry_price,
                        "pnl": p.pnl,
                        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                    }
                    for p in pos_records[-10:]
                ],
            }

    from monika.core.analytics.paper_tracker import PaperTracker

    tracker = PaperTracker(settings)
    stats = await tracker.get_statistics(effective_session, days_back=days_back, symbol=symbol)
    stats["mode"] = "paper"
    return stats


@register_tool(
    "get_paper_trading_performance",
    aliases=["paper_trading_performance", "paper_stats"],
    category="POSITION",
    parallel_safe=True,
)
class GetPaperTradingPerformanceHandler(ToolHandler):
    name = "get_paper_trading_performance"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_paper_trading_performance(args, session=session, executor=executor, **kwargs)


async def handle_get_portfolio_exposure(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    mode = str(args.get("mode", "all")).lower()
    is_paper = None
    if mode == "paper":
        is_paper = True
    elif mode == "live":
        is_paper = False
    elif "is_paper" in args:
        is_paper = bool(args["is_paper"])

    effective_session = session or getattr(executor, "session", None)

    async def _run(s: AsyncSession):
        from monika.application.services.portfolio_service import PortfolioService

        return await PortfolioService.get_portfolio_exposure(s, is_paper=is_paper)

    if effective_session:
        return await _run(effective_session)
    else:
        from monika.infrastructure.database.db import get_session

        async with get_session() as sess:
            return await _run(sess)


@register_tool(
    "get_portfolio_exposure",
    aliases=["portfolio_exposure", "portfolio_risk_exposure"],
    category="POSITION",
    parallel_safe=True,
)
class GetPortfolioExposureHandler(ToolHandler):
    name = "get_portfolio_exposure"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_portfolio_exposure(args, session=session, executor=executor, **kwargs)


async def handle_query_signal_performance(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Query trade signals joined with execution outcomes with flexible filters (confidence, outcome, days)."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for query_signal_performance"}

    min_confidence = float(args.get("min_confidence", 0.0))
    max_confidence = float(args.get("max_confidence", 1.0))
    outcome = str(args.get("outcome", "all")).lower().strip()
    symbol = (args.get("symbol") or "").upper().strip().replace("/", "")
    days_back = int(args.get("days_back", 30))
    limit = min(100, int(args.get("limit", 20)))

    from datetime import timedelta

    import monika.core.primitives.clock as clock

    cutoff = clock.now() - timedelta(days=days_back)

    stmt = (
        select(AssetAnalysis, PaperTradeRecord)
        .outerjoin(PaperTradeRecord, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(AssetAnalysis.generated_at >= cutoff)
        .where(AssetAnalysis.confidence >= min_confidence)
        .where(AssetAnalysis.confidence <= max_confidence)
    )
    if symbol:
        stmt = stmt.where(AssetAnalysis.symbol == symbol)

    if outcome == "win":
        stmt = stmt.where(PaperTradeRecord.pnl_pct > 0)
    elif outcome == "loss":
        stmt = stmt.where(PaperTradeRecord.pnl_pct <= 0)

    rows = (await effective_session.execute(stmt.order_by(desc(AssetAnalysis.generated_at)).limit(limit))).all()

    results = []
    for ana, trade in rows:
        results.append(
            {
                "analysis_id": ana.id,
                "symbol": ana.symbol,
                "decision": ana.decision,
                "confidence": ana.confidence,
                "confluence_score": ana.confluence_score,
                "generated_at": ana.generated_at.isoformat() if ana.generated_at else None,
                "rationale": (ana.rationale or "")[:200],
                "trade_id": trade.id if trade else None,
                "trade_status": trade.status if trade else None,
                "entry_price": trade.entry_price if trade else None,
                "exit_price": getattr(trade, "exit_price", None) if trade else None,
                "pnl_pct": trade.pnl_pct if trade else None,
                "exit_reason": getattr(trade, "exit_reason", None) if trade else None,
                "outcome": "win"
                if (trade and trade.pnl_pct is not None and trade.pnl_pct > 0)
                else ("loss" if trade and trade.pnl_pct is not None else "no_trade/open"),
            }
        )

    return {
        "query_filters": {
            "min_confidence": min_confidence,
            "max_confidence": max_confidence,
            "outcome": outcome,
            "symbol": symbol or "ALL",
            "days_back": days_back,
        },
        "count": len(results),
        "signals": results,
    }


@register_tool(
    "query_signal_performance", aliases=["query_signals", "signal_performance"], category="INTEL", parallel_safe=True
)
class QuerySignalPerformanceHandler(ToolHandler):
    name = "query_signal_performance"
    category = "INTEL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_query_signal_performance(args, session=session, executor=executor, **kwargs)


async def handle_get_pnl_summary(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Aggregate total profit/loss (real and paper) across today, this week, this month, and all-time."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for get_pnl_summary"}

    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    import monika.core.primitives.clock as clock
    from monika.infrastructure.database.models import PaperTradeRecord, Position

    now = clock.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())  # Monday 00:00
    month_start = today_start.replace(day=1)

    periods = {
        "today": today_start,
        "this_week": week_start,
        "this_month": month_start,
        "all_time": datetime(2000, 1, 1, tzinfo=timezone.utc),
    }

    results = {}
    try:
        for p_name, p_start in periods.items():
            # Real positions (closed)
            stmt_pos = select(
                func.coalesce(func.sum(Position.pnl), 0.0),
                func.count(Position.id),
                func.coalesce(func.sum(case((Position.pnl > 0, 1), else_=0)), 0),
            ).where(
                Position.status == "closed",
                Position.is_paper == False,
                Position.closed_at >= p_start,
            )
            res_pos = (await effective_session.execute(stmt_pos)).one_or_none()
            real_pnl, real_total, real_wins = res_pos if res_pos else (0.0, 0, 0)

            # Paper trades (closed)
            stmt_paper = select(
                func.coalesce(func.sum(Position.pnl), 0.0),
                func.count(Position.id),
                func.coalesce(func.sum(case((Position.pnl > 0, 1), else_=0)), 0),
            ).where(
                Position.status == "closed",
                Position.is_paper == True,
                Position.closed_at >= p_start,
            )
            res_paper = (await effective_session.execute(stmt_paper)).one_or_none()
            paper_pnl, paper_total, paper_wins = res_paper if res_paper else (0.0, 0, 0)

            results[p_name] = {
                "real": {
                    "total_pnl_usd": round(float(real_pnl or 0.0), 2),
                    "total_trades": int(real_total or 0),
                    "win_trades": int(real_wins or 0),
                    "win_rate_pct": round((float(real_wins or 0) / float(real_total) * 100), 1) if real_total else 0.0,
                },
                "paper": {
                    "total_pnl_usd": round(float(paper_pnl or 0.0), 2),
                    "total_trades": int(paper_total or 0),
                    "win_trades": int(paper_wins or 0),
                    "win_rate_pct": round((float(paper_wins or 0) / float(paper_total) * 100), 1)
                    if paper_total
                    else 0.0,
                },
            }

        return {
            "status": "success",
            "as_of": now.isoformat(),
            "summary": results,
        }
    except Exception as exc:
        logger.error(f"Error computing PnL summary: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}


@register_tool("get_pnl_summary", aliases=["pnl_summary", "get_total_pnl"], category="INTEL", parallel_safe=True)
class GetPnlSummaryHandler(ToolHandler):
    name = "get_pnl_summary"
    category = "INTEL"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_pnl_summary(args, session=session, executor=executor, **kwargs)


async def handle_get_broker_expenses_summary(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Aggregates broker expenses (commissions, swap charges, and financing fees) over a specified period (default 30 days)."""
    days = int(args.get("days", 30))
    symbol_filter = str(args.get("symbol") or "").upper().strip()

    from datetime import timedelta

    import monika.core.primitives.clock as clock

    now = clock.now()
    since = now - timedelta(days=days)

    total_commission = 0.0
    total_swap = 0.0
    total_fee = 0.0
    total_profit = 0.0
    deal_count = 0
    by_symbol: dict = {}

    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        mt5_client = get_mt5_client(getattr(executor, "settings", {}))
        deals = []
        mt5_lib = getattr(mt5_client, "mt5", None)
        if mt5_lib is not None:
            deals = mt5_lib.history_deals_get(since, now) or []
            if not deals:
                import MetaTrader5 as _mt5

                deals = _mt5.history_deals_get(since, now) or []

        for d in deals:
            sym = getattr(d, "symbol", "") or "UNKNOWN"
            if symbol_filter and sym != symbol_filter:
                continue
            comm = float(getattr(d, "commission", 0.0) or 0.0)
            swp = float(getattr(d, "swap", 0.0) or 0.0)
            fee = float(getattr(d, "fee", 0.0) or 0.0)
            prof = float(getattr(d, "profit", 0.0) or 0.0)

            total_commission += comm
            total_swap += swp
            total_fee += fee
            total_profit += prof
            deal_count += 1

            if sym not in by_symbol:
                by_symbol[sym] = {"commission": 0.0, "swap": 0.0, "fee": 0.0, "deals": 0}
            by_symbol[sym]["commission"] = round(by_symbol[sym]["commission"] + comm, 2)
            by_symbol[sym]["swap"] = round(by_symbol[sym]["swap"] + swp, 2)
            by_symbol[sym]["fee"] = round(by_symbol[sym]["fee"] + fee, 2)
            by_symbol[sym]["deals"] += 1

    except Exception as e:
        logger.debug(f"MT5 deal history fetch note: {e}")

    total_expenses = abs(total_commission) + abs(total_swap) + abs(total_fee)
    return {
        "status": "success",
        "period_days": days,
        "deals_analyzed": deal_count,
        "total_commission_usd": round(total_commission, 2),
        "total_swap_usd": round(total_swap, 2),
        "total_fee_usd": round(total_fee, 2),
        "total_expenses_usd": round(total_expenses, 2),
        "total_realized_profit_usd": round(total_profit, 2),
        "net_profit_after_expenses_usd": round(total_profit + total_commission + total_swap + total_fee, 2),
        "by_symbol": by_symbol,
        "note": f"Aggregated {deal_count} deals from MT5 history over the last {days} days.",
    }


@register_tool(
    "get_broker_expenses_summary",
    aliases=["get_commissions_and_swap", "broker_fees_summary"],
    category="POSITION",
    parallel_safe=True,
)
class GetBrokerExpensesSummaryHandler(ToolHandler):
    name = "get_broker_expenses_summary"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_broker_expenses_summary(args, session=session, executor=executor, **kwargs)


__all__ = [
    "handle_get_trade_history",
    "GetTradeHistoryHandler",
    "handle_get_trade_details",
    "GetTradeDetailsHandler",
    "handle_get_paper_trading_performance",
    "GetPaperTradingPerformanceHandler",
    "handle_get_portfolio_exposure",
    "GetPortfolioExposureHandler",
    "handle_query_signal_performance",
    "QuerySignalPerformanceHandler",
    "handle_get_pnl_summary",
    "GetPnlSummaryHandler",
    "handle_get_broker_expenses_summary",
    "GetBrokerExpensesSummaryHandler",
]
