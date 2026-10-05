# ==============================================================================
# File: analysis/tools/handlers/trade_intel.py
# ==============================================================================

"""
Trade intelligence and history tool handlers.
Direct execution without circular trampolines.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List
from sqlalchemy import select, desc, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AssetAnalysis, PaperTradeRecord, TradeTrigger, TelegramConversation, DecisionReflection, ActivityLog
import utils.clock as clock
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool, ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.TradeIntel")


def _get_session_and_settings(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    return session, settings


async def handle_get_trade_history(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    limit = int(args.get("limit", 10))
    status_filter = args.get("status")
    symbol = args.get("symbol")

    if not effective_session:
        return {"trades": [], "count": 0, "status": "no_session"}

    query = select(PaperTradeRecord)
    if status_filter:
        query = query.where(PaperTradeRecord.status == status_filter)
    if symbol:
        clean_sym = symbol.strip().upper().replace("/", "")
        query = query.where(PaperTradeRecord.symbol == clean_sym)
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
        from database.models import Position
        pos_q = select(Position)
        if status_filter:
            pos_q = pos_q.where(Position.status == status_filter)
        if symbol:
            clean_sym = symbol.strip().upper().replace("/", "")
            pos_q = pos_q.where(Position.symbol == clean_sym)
        pos_q = pos_q.order_by(desc(Position.opened_at)).limit(limit)
        pos_rows = (await effective_session.execute(pos_q)).scalars().all()
        for p in pos_rows:
            trades.append({
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
            })

    return {"count": len(trades), "trades": trades}


async def handle_get_trade_details(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    trade_id = args.get("trade_id") or args.get("id")
    if not trade_id:
        return {"error": "Missing trade_id"}
    if not effective_session:
        return {"status": "no_session"}

    try:
        tid = int(trade_id)
    except (ValueError, TypeError):
        return {"error": f"Invalid trade_id: {trade_id}"}

    record = (await effective_session.execute(
        select(PaperTradeRecord).where(PaperTradeRecord.id == tid)
    )).scalar_one_or_none()

    is_live = False
    if not record:
        from database.models import Position
        record = (await effective_session.execute(
            select(Position).where((Position.id == tid) | (Position.ticket == tid))
        )).scalar_one_or_none()
        if record:
            is_live = True

    if not record:
        return {"status": "not_found", "trade_id": tid}

    reflection_data = None
    analysis_id = getattr(record, "analysis_id", None)
    symbol = getattr(record, "symbol", "")
    try:
        ref_q = select(DecisionReflection).where(
            (DecisionReflection.session_id == str(analysis_id)) | (DecisionReflection.symbol == symbol)
        ).order_by(desc(DecisionReflection.created_at)).limit(1)
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
            ana_row = (await effective_session.execute(
                select(AssetAnalysis).where(AssetAnalysis.id == analysis_id)
            )).scalar_one_or_none()
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
        "opened_at": record.opened_at.isoformat() if getattr(record, "opened_at", None) else None,
        "closed_at": record.closed_at.isoformat() if getattr(record, "closed_at", None) else None,
        "reflection": reflection_data,
        "debate_analysis": debate_data,
    }


async def handle_create_price_alert(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    symbol = (args.get("symbol") or getattr(executor, "symbol", "") or "").strip().upper().replace('/', '')
    price_level = float(args.get("price_level") or 0.0)
    condition = (args.get("condition") or "above").lower()
    note = args.get("note") or "Ad-hoc user price alert"

    if not symbol or price_level <= 0:
        return {"error": "Valid symbol and positive price_level are required"}
    if not effective_session:
        return {"status": "no_session"}

    trigger = TradeTrigger(
        asset_analysis_id=None,
        trigger_type="price_level",
        condition_json=json.dumps({
            "symbol": symbol,
            "price": price_level,
            "target_price": price_level,
            "direction": condition,
            "condition": condition,
            "is_user_alert": True,
            "note": note,
        }),
        status="pending",
        created_at=clock.now(),
    )
    effective_session.add(trigger)
    await effective_session.commit()

    return {
        "status": "created",
        "trigger_id": trigger.id,
        "symbol": symbol,
        "condition": condition,
        "price_level": price_level,
        "message": f"Price alert #{trigger.id} berhasil dibuat untuk {symbol} saat harga {condition} {price_level}"
    }


async def handle_get_active_triggers(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"active_triggers": [], "count": 0, "status": "no_session"}

    symbol = args.get("symbol")
    query = (
        select(TradeTrigger, AssetAnalysis)
        .outerjoin(AssetAnalysis, TradeTrigger.asset_analysis_id == AssetAnalysis.id)
        .where(TradeTrigger.status == "pending")
    )
    if symbol:
        clean_sym = symbol.strip().upper().replace("/", "")
        query = query.where(
            or_(
                AssetAnalysis.symbol == clean_sym,
                TradeTrigger.condition_json.like(f"%{clean_sym}%")
            )
        )
    query = query.order_by(desc(TradeTrigger.created_at)).limit(20)

    rows = (await effective_session.execute(query)).all()
    triggers = []
    for trigger, analysis in rows:
        cond = {}
        if trigger.condition_json:
            try:
                cond = json.loads(trigger.condition_json)
            except Exception:
                pass
        sym = (analysis.symbol if analysis else None) or cond.get("symbol", "UNKNOWN")
        direction = cond.get("direction") or (getattr(analysis, "decision", None) if analysis else None)
        triggers.append({
            "id": trigger.id,
            "symbol": sym,
            "trigger_type": trigger.trigger_type,
            "condition_type": cond.get("condition_type", trigger.trigger_type),
            "trigger_price": cond.get("price") or cond.get("price_level") or cond.get("trigger_price") or cond.get("target_price"),
            "direction": direction,
            "created_at": trigger.created_at.isoformat() if trigger.created_at else None,
            "condition": cond,
        })
    return {"count": len(triggers), "active_triggers": triggers}


async def handle_get_paper_trading_performance(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"status": "no_session"}

    days_back = args.get("days_back") or args.get("days")
    if days_back is not None:
        try:
            days_back = int(days_back)
        except (ValueError, TypeError):
            days_back = None
    symbol = args.get("symbol")
    mode = str(args.get("mode", "paper")).lower()

    if mode in ("live", "all"):
        from database.models import Position
        from datetime import timedelta
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
                ]
            }

    from utils.analytics.paper_tracker import PaperTracker
    tracker = PaperTracker(settings)
    stats = await tracker.get_statistics(effective_session, days_back=days_back, symbol=symbol)
    stats["mode"] = "paper"
    return stats


async def handle_get_conversation_history(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    limit = int(args.get("limit", 10))
    if not effective_session:
        return {"history": []}
    rows = (await effective_session.execute(
        select(TelegramConversation).order_by(desc(TelegramConversation.timestamp)).limit(limit)
    )).scalars().all()
    return {
        "history": [
            {
                "role": r.role,
                "message": r.message,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in reversed(rows)
        ]
    }


async def handle_get_spread_snapshot(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    sym = args.get("symbol") or getattr(executor, "symbol", "EURUSD")
    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        return await client.get_spread(symbol=sym)
    except Exception as e:
        return {"symbol": sym, "spread_points": 0, "error": str(e)}


async def handle_get_market_correlations(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Calculates rolling cross-asset return correlations across market symbols."""
    from database.db import get_session
    from risk.correlation_matrix import DynamicCorrelationMatrix
    import utils.clock as clock

    symbols = args.get("symbols")
    if isinstance(symbols, str):
        symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbols or not isinstance(symbols, list):
        symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]

    effective_session = session or getattr(executor, "session", None)
    matrix_calc = DynamicCorrelationMatrix()

    try:
        if effective_session:
            matrix = await matrix_calc.get_matrix(effective_session, symbols)
        else:
            async with get_session() as sess:
                matrix = await matrix_calc.get_matrix(sess, symbols)
    except Exception as e:
        logger.warning(f"Error computing market correlation matrix: {e}")
        matrix = {}

    return {
        "status": "available",
        "symbols": symbols,
        "correlation_matrix": matrix,
        "timestamp": clock.now().isoformat(),
    }


@register_tool("get_market_correlations", aliases=["market_correlations", "currency_correlation"], category="MARKET_DATA", parallel_safe=True)
class GetMarketCorrelationsHandler(ToolHandler):
    name = "get_market_correlations"
    category = "MARKET_DATA"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_market_correlations(args, session=session, executor=executor, **kwargs)



@register_tool("get_trade_history", aliases=["trade_history"], category="POSITION", parallel_safe=True)
class GetTradeHistoryHandler(ToolHandler):
    name = "get_trade_history"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_trade_history(args, session=session, executor=executor, **kwargs)


@register_tool("get_trade_details", aliases=["trade_details"], category="POSITION", parallel_safe=True)
class GetTradeDetailsHandler(ToolHandler):
    name = "get_trade_details"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_trade_details(args, session=session, executor=executor, **kwargs)


@register_tool("get_active_triggers", aliases=["active_triggers"], category="EXECUTION", parallel_safe=True)
class GetActiveTriggersHandler(ToolHandler):
    name = "get_active_triggers"
    category = "EXECUTION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_active_triggers(args, session=session, executor=executor, **kwargs)


@register_tool("create_price_alert", aliases=["price_alert", "set_price_alert"], category="EXECUTION", parallel_safe=False)
class CreatePriceAlertHandler(ToolHandler):
    name = "create_price_alert"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_create_price_alert(args, session=session, executor=executor, **kwargs)


@register_tool("get_paper_trading_performance", aliases=["paper_trading_performance", "paper_stats"], category="POSITION", parallel_safe=True)
class GetPaperTradingPerformanceHandler(ToolHandler):
    name = "get_paper_trading_performance"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_paper_trading_performance(args, session=session, executor=executor, **kwargs)


@register_tool("get_asset_analysis", aliases=["asset_analysis"], category="ANALYSIS", parallel_safe=True)
class GetAssetAnalysisHandler(ToolHandler):
    name = "get_asset_analysis"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_asset_analysis(args, session=session, executor=executor, **kwargs)


@register_tool("get_recent_activity", aliases=["recent_activity"], category="SYSTEM", parallel_safe=True)
class GetRecentActivityHandler(ToolHandler):
    name = "get_recent_activity"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_recent_activity(args, session=session, executor=executor, **kwargs)


@register_tool("get_conversation_history", aliases=["conversation_history"], category="SYSTEM", parallel_safe=True)
class GetConversationHistoryHandler(ToolHandler):
    name = "get_conversation_history"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_conversation_history(args, session=session, executor=executor, **kwargs)


async def handle_get_recent_activity(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Recent agent activity log entries."""
    from database.models import ActivityLog
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for get_recent_activity"}
    limit = int(args.get("limit", 10))
    rows = (await effective_session.execute(
        select(ActivityLog).order_by(desc(ActivityLog.timestamp)).limit(limit)
    )).scalars().all()
    return {
        "activity": [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "category": r.category,
                "description": r.description,
            }
            for r in rows
        ]
    }


async def handle_get_asset_analysis(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Latest or historical per-asset analysis decisions for a symbol."""
    effective_session = session or getattr(executor, "session", None)
    symbol = (args.get("symbol") or getattr(executor, "symbol", "") or "").upper().strip().replace('/', '')
    if not effective_session:
        return {"error": "Database session required for get_asset_analysis"}

    limit = min(50, max(1, int(args.get("limit", 1))))
    target_date = args.get("target_date") or args.get("date")
    hours_back = args.get("hours_back")

    stmt = select(AssetAnalysis)
    if symbol:
        stmt = stmt.where(AssetAnalysis.symbol == symbol)

    if target_date:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(target_date).replace('Z', '+00:00'))
            stmt = stmt.where(AssetAnalysis.generated_at <= dt)
        except Exception:
            pass
    elif hours_back:
        try:
            import utils.clock as clock
            from datetime import timedelta
            cutoff = clock.now() - timedelta(hours=float(hours_back))
            stmt = stmt.where(AssetAnalysis.generated_at >= cutoff)
        except Exception:
            pass

    rows = (await effective_session.execute(
        stmt.order_by(desc(AssetAnalysis.generated_at)).limit(limit)
    )).scalars().all()

    if not rows:
        return {"symbol": symbol or "ALL", "status": "no_analysis", "message": f"No stored analysis found for {symbol}."}

    def _fmt(r):
        return {
            "id": r.id,
            "symbol": r.symbol,
            "decision": r.decision,
            "confidence": r.confidence,
            "entry_zone": r.entry_zone,
            "stop_loss": r.stop_loss,
            "take_profit": r.take_profit,
            "rationale": r.rationale,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "debate_verdict": r.debate_verdict,
            "debate_reason": r.debate_reason,
            "debate_bull_thesis": r.debate_bull_thesis,
            "debate_bear_dissent": r.debate_bear_dissent,
            "risk_multiplier": r.risk_multiplier,
            "decision_source": r.decision_source,
            "arbitration_reason": getattr(r, "arbitration_reason", None),
            "confluence_score": r.confluence_score,
            "market_regime": r.market_regime_at_analysis,
        }

    if limit == 1 and not (target_date or hours_back):
        return _fmt(rows[0])

    return {
        "symbol": symbol or "ALL",
        "count": len(rows),
        "analyses": [_fmt(r) for r in rows],
    }


async def handle_search_historical_memories(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Searches past decisions, reflections, lessons, and precedent trade sessions."""
    from analysis.memory.session_search import SessionSearchEngine
    effective_session = session or getattr(executor, "session", None)
    query = str(args.get("query") or "").strip()
    symbol = args.get("symbol")
    limit = int(args.get("limit", 5))
    engine = SessionSearchEngine()
    if symbol:
        results = await engine.get_symbol_precedents(symbol=symbol, limit=limit, session=effective_session)
    else:
        results = await engine.search(query=query, limit=limit, session=effective_session)
    return {"query": query, "symbol": symbol, "count": len(results), "results": results}


@register_tool("search_historical_memories")
class SearchHistoricalMemoriesHandler(ToolHandler):
    name = "search_historical_memories"

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_search_historical_memories(args, session=session, executor=executor, **kwargs)


async def handle_run_trade_counterfactual(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Runs counterfactual replay on a specific past trade."""
    from analysis.memory.counterfactual_simulator import CounterfactualSimulator
    from database.db import get_session

    trade_id = int(args.get("trade_id", 0))
    sl_pips_delta = float(args.get("sl_pips_delta", 0.0))
    tp_pips_delta = float(args.get("tp_pips_delta", 0.0))

    if not trade_id:
        return {"status": "error", "message": "Missing 'trade_id' parameter."}

    simulator = CounterfactualSimulator()
    if session:
        return await simulator.simulate_single_trade_counterfactual(
            session=session,
            trade_id=trade_id,
            sl_pips_delta=sl_pips_delta,
            tp_pips_delta=tp_pips_delta,
        )
    else:
        async with get_session() as sess:
            return await simulator.simulate_single_trade_counterfactual(
                session=sess,
                trade_id=trade_id,
                sl_pips_delta=sl_pips_delta,
                tp_pips_delta=tp_pips_delta,
            )


@register_tool("run_trade_counterfactual", aliases=["trade_counterfactual", "counterfactual_replay"])
class RunTradeCounterfactualHandler(ToolHandler):
    name = "run_trade_counterfactual"

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_trade_counterfactual(args, session=session, executor=executor, **kwargs)


async def handle_get_debate_statistics(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Aggregates debate outcomes (Bull vs Bear wins) over a specified time window."""
    from database.db import get_session
    from database.models import AssetAnalysis
    from datetime import timedelta
    import utils.clock as clock

    days = int(args.get("days", 30))
    cutoff = clock.now() - timedelta(days=days)

    effective_session = session or getattr(executor, "session", None)

    async def _query(sess):
        stmt = (
            select(AssetAnalysis)
            .where(AssetAnalysis.generated_at >= cutoff)
            .where(AssetAnalysis.debate_verdict.isnot(None))
            .order_by(desc(AssetAnalysis.generated_at))
        )
        rows = (await sess.execute(stmt)).scalars().all()

        total = len(rows)
        bull_wins = 0
        bear_wins = 0
        avoid_count = 0
        symbol_counts = {}

        for r in rows:
            verd = str(r.debate_verdict or "").lower()
            sym = str(r.symbol or "UNKNOWN")
            symbol_counts[sym] = symbol_counts.get(sym, 0) + 1
            if "buy" in verd or "bull" in verd:
                bull_wins += 1
            elif "sell" in verd or "bear" in verd:
                bear_wins += 1
            else:
                avoid_count += 1

        bull_pct = round((bull_wins / total * 100), 1) if total > 0 else 0.0
        bear_pct = round((bear_wins / total * 100), 1) if total > 0 else 0.0

        return {
            "status": "success",
            "period_days": days,
            "total_debates": total,
            "bull_wins": bull_wins,
            "bear_wins": bear_wins,
            "neutral_or_avoid": avoid_count,
            "bull_win_rate_pct": bull_pct,
            "bear_win_rate_pct": bear_pct,
            "symbols_evaluated": symbol_counts,
        }

    if effective_session:
        return await _query(effective_session)
    else:
        async with get_session() as sess:
            return await _query(sess)


@register_tool("get_debate_statistics", aliases=["debate_stats", "debate_outcomes_summary"], category="ANALYSIS", parallel_safe=True)
class GetDebateStatisticsHandler(ToolHandler):
    name = "get_debate_statistics"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_debate_statistics(args, session=session, executor=executor, **kwargs)


async def handle_get_rejection_history(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Retrieves history of orders rejected by RiskGate or preflight safety checks."""
    from database.db import get_session
    from database.models import OrderLog
    import json

    limit = int(args.get("limit", 20))
    symbol = args.get("symbol")
    effective_session = session or getattr(executor, "session", None)

    async def _query(sess):
        from sqlalchemy import or_
        days_back = int(args.get("days_back", 30))
        cutoff = clock.now() - timedelta(days=days_back)
        stmt = (
            select(OrderLog)
            .where(
                OrderLog.timestamp >= cutoff,
                or_(
                    OrderLog.approved_by.is_(None),
                    OrderLog.approved_by != "risk_gate",
                    OrderLog.result.ilike("%reject%"),
                    OrderLog.result.ilike("%failed%"),
                    OrderLog.result.ilike("%breach%")
                )
            )
            .order_by(desc(OrderLog.timestamp))
            .limit(limit)
        )
        if symbol:
            stmt = stmt.where(OrderLog.symbol == symbol.strip().upper())

        rows = (await sess.execute(stmt)).scalars().all()
        rejections = []
        for r in rows:
            meta = {}
            if r.result:
                try:
                    meta = json.loads(r.result) if isinstance(r.result, str) else r.result
                except Exception:
                    meta = {"raw_result": r.result}
            params = {}
            if r.params_json:
                try:
                    params = json.loads(r.params_json) if isinstance(r.params_json, str) else r.params_json
                except Exception:
                    params = {}

            reasons = (
                meta.get("rejection_reasons")
                or meta.get("checks_failed")
                or meta.get("reason")
                or meta.get("error")
                or [meta.get("raw_result") or r.action]
            )
            if isinstance(reasons, str):
                reasons = [reasons]

            rejections.append({
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "symbol": r.symbol,
                "action": r.action,
                "requested_by": r.requested_by,
                "approved_by": r.approved_by,
                "reasons": reasons,
                "params": params,
                "details": meta,
            })
        return {
            "status": "success",
            "total_retrieved": len(rejections),
            "rejections": rejections,
        }

    if effective_session:
        return await _query(effective_session)
    else:
        async with get_session() as sess:
            return await _query(sess)


@register_tool("get_rejection_history", aliases=["rejection_history", "rejected_orders"], category="RISK", parallel_safe=True)
class GetRejectionHistoryHandler(ToolHandler):
    name = "get_rejection_history"
    category = "RISK"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_rejection_history(args, session=session, executor=executor, **kwargs)


async def handle_get_market_chronicle(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Retrieve market chronicles and macro structural milestones for a given month, timeframe, or category."""
    from database.db import get_session
    from database.models import MarketChronicle
    from datetime import datetime, timezone
    import calendar

    month = args.get("month")
    year = int(args.get("year", datetime.now(timezone.utc).year))
    category = args.get("category")
    limit = int(args.get("limit", 20))
    effective_session = session or getattr(executor, "session", None)

    month_num = None
    if isinstance(month, int):
        month_num = month
    elif isinstance(month, str) and month.strip():
        m_str = month.strip().lower()
        month_names = {
            "januari": 1, "january": 1, "jan": 1,
            "februari": 2, "february": 2, "feb": 2,
            "maret": 3, "march": 3, "mar": 3,
            "april": 4, "apr": 4,
            "mei": 5, "may": 5,
            "juni": 6, "june": 6, "jun": 6,
            "juli": 7, "july": 7, "jul": 7,
            "agustus": 8, "august": 8, "aug": 8,
            "september": 9, "sep": 9,
            "oktober": 10, "october": 10, "oct": 10,
            "november": 11, "nov": 11,
            "desember": 12, "december": 12, "dec": 12,
        }
        month_num = month_names.get(m_str)

    async def _query(sess):
        stmt = select(MarketChronicle).order_by(desc(MarketChronicle.event_date))
        if month_num:
            _, last_day = calendar.monthrange(year, month_num)
            start_dt = datetime(year, month_num, 1, tzinfo=timezone.utc)
            end_dt = datetime(year, month_num, last_day, 23, 59, 59, tzinfo=timezone.utc)
            stmt = stmt.where(MarketChronicle.event_date >= start_dt).where(MarketChronicle.event_date <= end_dt)
        if category:
            stmt = stmt.where(MarketChronicle.category.ilike(f"%{category}%"))
        stmt = stmt.limit(limit)

        rows = (await sess.execute(stmt)).scalars().all()
        chronicles = []
        for r in rows:
            chronicles.append({
                "id": r.id,
                "event_date": r.event_date.isoformat() if r.event_date else None,
                "category": r.category,
                "headline": r.headline,
                "narrative": r.narrative,
                "status": getattr(r, "status", "active"),
                "affected_assets": getattr(r, "affected_assets", None),
            })
        return {
            "status": "success",
            "year": year,
            "month": month,
            "total_chronicles": len(chronicles),
            "chronicles": chronicles,
        }

    if effective_session:
        return await _query(effective_session)
    else:
        async with get_session() as sess:
            return await _query(sess)


@register_tool("get_market_chronicle", aliases=["market_chronicle", "trading_chronicle", "chronicle"], category="KNOWLEDGE", parallel_safe=True)
class GetMarketChronicleHandler(ToolHandler):
    name = "get_market_chronicle"
    category = "KNOWLEDGE"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_market_chronicle(args, session=session, executor=executor, **kwargs)


async def handle_get_portfolio_exposure(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
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
        from services.portfolio_service import PortfolioService
        return await PortfolioService.get_portfolio_exposure(s, is_paper=is_paper)

    if effective_session:
        return await _run(effective_session)
    else:
        from database.db import get_session
        async with get_session() as sess:
            return await _run(sess)


@register_tool("get_portfolio_exposure", aliases=["portfolio_exposure", "portfolio_risk_exposure"], category="POSITION", parallel_safe=True)
class GetPortfolioExposureHandler(ToolHandler):
    name = "get_portfolio_exposure"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_portfolio_exposure(args, session=session, executor=executor, **kwargs)


async def handle_run_monte_carlo_simulation(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    from backtest.monte_carlo_engine import MonteCarloStressTester
    from services.portfolio_service import PortfolioService

    num_simulations = int(args.get("num_simulations", 1000))
    mode = str(args.get("mode", "permutation"))
    initial_equity = float(args.get("initial_equity", 10000.0))
    symbol = args.get("symbol")
    target_dd_raw = args.get("target_drawdown_pct") or args.get("ruin_drawdown_pct")
    if target_dd_raw is not None:
        try:
            target_dd_val = float(target_dd_raw)
            ruin_drawdown_pct = target_dd_val / 100.0 if target_dd_val > 1.0 else target_dd_val
        except (ValueError, TypeError):
            ruin_drawdown_pct = 0.50
    else:
        ruin_drawdown_pct = 0.50

    effective_session = session or getattr(executor, "session", None)

    async def _run(s: AsyncSession):
        closed = await PortfolioService.get_closed_positions(s, limit=200, symbol=symbol)
        returns = []
        for p in closed:
            if p.pnl is not None and initial_equity > 0:
                returns.append(float(p.pnl) / initial_equity)
            elif getattr(p, "pnl_pct", None) is not None:
                returns.append(float(p.pnl_pct) / 100.0)

        # Fallback to PaperTradeRecord if live closed positions are insufficient
        if len(returns) < 5:
            try:
                from database.models import PaperTradeRecord
                paper_stmt = select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")
                if symbol:
                    paper_stmt = paper_stmt.where(PaperTradeRecord.symbol == symbol.upper())
                paper_trades = (await s.execute(paper_stmt.order_by(PaperTradeRecord.closed_at.desc()).limit(200))).scalars().all()
                for pt in paper_trades:
                    if pt.pnl_pct is not None:
                        returns.append(float(pt.pnl_pct) / 100.0)
                    elif pt.entry_price and pt.exit_price:
                        mult = 1.0 if pt.direction == "buy" else -1.0
                        pnl_fraction = ((pt.exit_price - pt.entry_price) / pt.entry_price) * mult
                        returns.append(pnl_fraction)
            except Exception as paper_err:
                logger.debug(f"Paper trades query for Monte Carlo notice: {paper_err}")

        sample_source = "database_trades" if len(returns) >= 5 else "synthetic_baseline_50_trades"
        if len(returns) < 5:
            import random
            rng = random.Random(42)
            returns = [0.018 if rng.random() < 0.55 else -0.01 for _ in range(50)]

        tester = MonteCarloStressTester(seed=42)
        res = tester.simulate_trade_sequence(
            trade_returns=returns,
            num_simulations=num_simulations,
            initial_equity=initial_equity,
            ruin_drawdown_pct=ruin_drawdown_pct,
            mode=mode,
        )
        res["sample_source"] = sample_source
        res["sample_trades_count"] = len(returns)
        res["symbol_filter"] = symbol or "ALL"
        res["target_drawdown_pct"] = round(ruin_drawdown_pct * 100.0, 2)
        res["target_drawdown_probability_pct"] = res.get("ruin_probability_pct", 0.0)
        return res

    if effective_session:
        return await _run(effective_session)
    else:
        from database.db import get_session
        async with get_session() as sess:
            return await _run(sess)


@register_tool("run_monte_carlo_simulation", aliases=["monte_carlo_simulation", "monte_carlo"], category="POSITION", parallel_safe=True)
class RunMonteCarloSimulationHandler(ToolHandler):
    name = "run_monte_carlo_simulation"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_monte_carlo_simulation(args, session=session, executor=executor, **kwargs)


async def handle_query_signal_performance(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Query trade signals joined with execution outcomes with flexible filters (confidence, outcome, days)."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for query_signal_performance"}

    min_confidence = float(args.get("min_confidence", 0.0))
    max_confidence = float(args.get("max_confidence", 1.0))
    outcome = str(args.get("outcome", "all")).lower().strip()
    symbol = (args.get("symbol") or "").upper().strip().replace('/', '')
    days_back = int(args.get("days_back", 30))
    limit = min(100, int(args.get("limit", 20)))

    import utils.clock as clock
    from datetime import timedelta
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
        results.append({
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
            "outcome": "win" if (trade and trade.pnl_pct is not None and trade.pnl_pct > 0) else ("loss" if trade and trade.pnl_pct is not None else "no_trade/open"),
        })

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


@register_tool("query_signal_performance", aliases=["query_signals", "signal_performance"], category="INTEL", parallel_safe=True)
class QuerySignalPerformanceHandler(ToolHandler):
    name = "query_signal_performance"
    category = "INTEL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_query_signal_performance(args, session=session, executor=executor, **kwargs)


async def handle_get_latest_risk_verdict(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Retrieve detailed RiskGate rejection reasons and checks passed/failed for latest trade attempt."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for get_latest_risk_verdict"}

    symbol = (args.get("symbol") or getattr(executor, "symbol", "") or "").upper().strip().replace('/', '')
    
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.category.in_(["trading", "risk"]))
        .order_by(desc(ActivityLog.timestamp))
        .limit(25)
    )
    rows = (await effective_session.execute(stmt)).scalars().all()

    matched = []
    for r in rows:
        desc_text = r.description or ""
        if not symbol or symbol in desc_text:
            matched.append({
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "category": r.category,
                "summary": desc_text,
                "actor": r.actor,
            })
            if len(matched) >= 5:
                break

    return {
        "symbol": symbol or "ALL",
        "recent_risk_events": matched,
        "count": len(matched),
    }


@register_tool("get_latest_risk_verdict", aliases=["trade_rejection_reason", "risk_rejection_details"], category="RISK", parallel_safe=True)
class GetLatestRiskVerdictHandler(ToolHandler):
    name = "get_latest_risk_verdict"
    category = "RISK"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_latest_risk_verdict(args, session=session, executor=executor, **kwargs)


async def handle_export_debate_transcripts(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Export specialist Bull/Bear debate theses and verdicts to JSON for fine-tuning or external audit."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for export_debate_transcripts"}

    days_back = int(args.get("days_back", 30))
    symbol = (args.get("symbol") or "").upper().strip().replace('/', '')
    limit = min(500, int(args.get("limit", 100)))

    import utils.clock as clock
    from datetime import timedelta
    cutoff = clock.now() - timedelta(days=days_back)

    stmt = (
        select(AssetAnalysis)
        .where(AssetAnalysis.generated_at >= cutoff)
        .where(AssetAnalysis.debate_verdict.isnot(None))
    )
    if symbol:
        stmt = stmt.where(AssetAnalysis.symbol == symbol)

    rows = (await effective_session.execute(stmt.order_by(desc(AssetAnalysis.generated_at)).limit(limit))).scalars().all()

    datasets = []
    for r in rows:
        datasets.append({
            "analysis_id": r.id,
            "symbol": r.symbol,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "decision": r.decision,
            "confidence": r.confidence,
            "bull_advocate_thesis": r.debate_bull_thesis,
            "bear_dissent_thesis": r.debate_bear_dissent,
            "judge_verdict": r.debate_verdict,
            "judge_rationale": r.debate_reason,
            "confluence_score": r.confluence_score,
            "sharegpt_conversation": [
                {"from": "human", "value": f"Analyze market structure and macroeconomic outlook for {r.symbol}."},
                {"from": "bull_agent", "value": r.debate_bull_thesis or "N/A"},
                {"from": "bear_agent", "value": r.debate_bear_dissent or "N/A"},
                {"from": "judge", "value": f"Verdict: {r.debate_verdict}. Rationale: {r.debate_reason or r.rationale}"}
            ]
        })

    return {
        "count": len(datasets),
        "days_back": days_back,
        "symbol": symbol or "ALL",
        "export_data": datasets,
    }


@register_tool("export_debate_transcripts", aliases=["export_debates"], category="INTEL", parallel_safe=True)
class ExportDebateTranscriptsHandler(ToolHandler):
    name = "export_debate_transcripts"
    category = "INTEL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_export_debate_transcripts(args, session=session, executor=executor, **kwargs)


async def handle_trigger_learning_cycle(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Manually trigger post-trade reflection, negative constraint generation, and playbook consolidation."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for trigger_learning_cycle"}

    settings = kwargs.get("settings") or getattr(executor, "settings", {}) or {}
    days_back = int(args.get("days_back", 7))

    try:
        from analysis.memory.reflector import TradeReflector
        from analysis.memory.negative_constraint_generator import NegativeConstraintGenerator
        from analysis.memory.lesson_consolidator import consolidate_lessons_to_playbook
        from database.models import DecisionReflection
        from sqlalchemy import select
        from datetime import timedelta
        import utils.clock as clock

        reflector = TradeReflector(settings)
        since = clock.now() - timedelta(days=days_back)
        q = (
            select(DecisionReflection)
            .where(DecisionReflection.status == "pending")
            .where(DecisionReflection.created_at >= since)
            .limit(20)
        )
        pending_rows = (await effective_session.execute(q)).scalars().all()
        reflected_count = 0
        for r in pending_rows:
            try:
                await reflector.reflect_on_trade(effective_session, r.id)
                reflected_count += 1
            except Exception as ref_err:
                logger.warning(f"Error reflecting on trade {r.id}: {ref_err}")

        symbols = settings.get("trading", {}).get("asset_universe", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
        total_constraints = 0
        for sym in symbols:
            try:
                c = await NegativeConstraintGenerator.generate_negative_constraints_from_losses(
                    session=effective_session, symbol=sym, max_constraints=2
                )
                total_constraints += len(c)
            except Exception as neg_err:
                logger.warning(f"Error generating negative constraints for {sym}: {neg_err}")

        consolidated_res = await consolidate_lessons_to_playbook(effective_session, settings, auto_propose_only=True)

        return {
            "status": "completed",
            "reflected_trades_count": reflected_count,
            "new_negative_constraints": total_constraints,
            "consolidated_playbook": "updated" if consolidated_res else "insufficient_data_to_cluster",
            "message": f"Learning cycle successfully executed across last {days_back} days."
        }
    except Exception as e:
        logger.error(f"Trigger learning cycle failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@register_tool("trigger_learning_cycle", aliases=["run_learning_cycle"], category="SYSTEM", parallel_safe=False)
class TriggerLearningCycleHandler(ToolHandler):
    name = "trigger_learning_cycle"
    category = "SYSTEM"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_trigger_learning_cycle(args, session=session, executor=executor, **kwargs)


async def handle_trigger_market_scan(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Trigger ad-hoc market opportunity scan across symbols and return top ranked opportunities."""
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"error": "Database session required for trigger_market_scan"}

    symbols = args.get("symbols") or settings.get("trading", {}).get("asset_universe", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",")]

    from database.models import FundamentalBrief, AssetAnalysis
    import json

    latest_brief = (await effective_session.execute(
        select(FundamentalBrief).order_by(desc(FundamentalBrief.generated_at)).limit(1)
    )).scalar_one_or_none()

    latest_analyses = []
    for sym in symbols:
        clean = sym.strip().upper().replace("/", "")
        ana = (await effective_session.execute(
            select(AssetAnalysis)
            .where(AssetAnalysis.symbol == clean)
            .order_by(desc(AssetAnalysis.generated_at))
            .limit(1)
        )).scalar_one_or_none()
        if ana:
            latest_analyses.append(ana)

    brief_data = {}
    if latest_brief and latest_brief.structured_json:
        try:
            brief_data = json.loads(latest_brief.structured_json)
        except Exception:
            pass

    recommendations = []
    for a in latest_analyses:
        rec = {
            "symbol": a.symbol,
            "decision": a.decision,
            "confidence": a.confidence,
            "confluence_score": a.confluence_score,
            "entry_zone": a.entry_zone,
            "stop_loss": a.stop_loss,
            "take_profit": a.take_profit,
            "rationale": a.rationale[:200] if a.rationale else "",
            "generated_at": a.generated_at.isoformat() if a.generated_at else None,
        }
        recommendations.append(rec)

    recommendations.sort(key=lambda r: (r.get("confidence") or 0.0, r.get("confluence_score") or 0.0), reverse=True)

    return {
        "status": "success",
        "market_regime": latest_brief.risk_sentiment if latest_brief else "unknown",
        "brief_confidence": latest_brief.confidence if latest_brief else 0.0,
        "brief_generated_at": latest_brief.generated_at.isoformat() if latest_brief and latest_brief.generated_at else None,
        "macro_themes": brief_data.get("macro_themes", []),
        "currency_rankings": brief_data.get("currency_rankings", {}),
        "top_recommendations": recommendations,
        "total_symbols_scanned": len(recommendations),
    }


@register_tool("trigger_market_scan", aliases=["scan_market_opportunities", "recommend_best_pairs"], category="ANALYSIS", parallel_safe=True)
class TriggerMarketScanHandler(ToolHandler):
    name = "trigger_market_scan"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_trigger_market_scan(args, session=session, executor=executor, **kwargs)


async def handle_run_strategy_backtest(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Run isolated point-in-time strategy backtest on historical data."""
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"error": "Database session required for run_strategy_backtest"}

    symbol = (args.get("symbol") or "EURUSD").upper().strip().replace("/", "")
    timeframe = str(args.get("timeframe", "H1")).upper()
    days_back = int(args.get("days_back", 90))
    strategy_name = str(args.get("strategy") or "smc_fvg").lower()

    try:
        from backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness
        from analysis.strategies.registry import STRATEGY_REGISTRY, EdgeStrategy

        # Resolve strategy class or fallback to base
        strategy_cls = None
        for k, v in STRATEGY_REGISTRY.items():
            if strategy_name in k.lower() or k.lower() in strategy_name:
                strategy_cls = v
                break

        if strategy_cls is None:
            for k, v in STRATEGY_REGISTRY.items():
                if isinstance(v, type) and issubclass(v, EdgeStrategy):
                    strategy_cls = v
                    break

        if strategy_cls is None:
            return {"status": "error", "message": f"Strategy '{strategy_name}' not found in registry."}

        harness = IsolatedStrategyBacktestHarness(
            strategy_cls=strategy_cls,
            symbol=symbol,
            settings=settings,
        )

        import utils.clock as clock
        from datetime import timedelta, datetime, timezone

        raw_start = args.get("start_date")
        raw_end = args.get("end_date")

        end_date = clock.now()
        if raw_end:
            try:
                end_date = datetime.fromisoformat(str(raw_end)).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        if raw_start:
            try:
                start_date = datetime.fromisoformat(str(raw_start)).replace(tzinfo=timezone.utc)
            except Exception:
                start_date = end_date - timedelta(days=days_back)
        else:
            start_date = end_date - timedelta(days=days_back)

        metrics = await harness.run_simulation(
            session=effective_session,
            start_date=start_date,
            end_date=end_date,
            lookback_candles=min(5000, days_back * 24),
        )

        return {
            "status": "success",
            "symbol": symbol,
            "strategy": strategy_cls.__name__ if hasattr(strategy_cls, "__name__") else strategy_name,
            "timeframe": timeframe,
            "days_back": days_back,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_trades": metrics.total_trades,
            "win_rate_pct": round(metrics.win_rate_pct, 2),
            "profit_factor": round(metrics.profit_factor, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
            "sortino_ratio": round(metrics.sortino_ratio, 2),
            "calmar_ratio": round(getattr(metrics, "calmar_ratio", 0.0), 2),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 2),
            "total_pnl_pct": round(metrics.total_pnl_pct, 2),
            "sample_trades": [
                {
                    "direction": t.direction,
                    "entry_time": t.entry_time.isoformat() if hasattr(t.entry_time, "isoformat") else str(t.entry_time),
                    "exit_time": t.exit_time.isoformat() if hasattr(t.exit_time, "isoformat") else str(t.exit_time),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl_pct": round(t.pnl_pct, 3),
                    "exit_reason": t.exit_reason,
                }
                for t in metrics.trades[-10:]
            ] if hasattr(metrics, "trades") and metrics.trades else [],
        }
    except Exception as e:
        logger.error(f"Strategy backtest failed for {symbol}: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "symbol": symbol, "strategy": strategy_name}


@register_tool("run_strategy_backtest", aliases=["backtest_strategy", "run_backtest"], category="ANALYSIS", parallel_safe=True)
class RunStrategyBacktestHandler(ToolHandler):
    name = "run_strategy_backtest"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_strategy_backtest(args, session=session, executor=executor, **kwargs)


async def handle_get_pnl_summary(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Aggregate total profit/loss (real and paper) across today, this week, this month, and all-time."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for get_pnl_summary"}

    import utils.clock as clock
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func
    from database.models import Position, PaperTradeRecord

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
                    "win_rate_pct": round((float(paper_wins or 0) / float(paper_total) * 100), 1) if paper_total else 0.0,
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

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_pnl_summary(args, session=session, executor=executor, **kwargs)


async def handle_run_adhoc_symbol_debate(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Runs an ad-hoc Multi-Agent Debate (Bull Specialist vs Bear Specialist vs Investment Judge) for a symbol."""
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    symbol = (args.get("symbol") or getattr(executor, "symbol", "EURUSD") or "EURUSD").upper().strip().replace("/", "")

    from database.db import get_session
    from analysis.debate.debate_orchestrator import DebateOrchestrator
    from analysis.prefetch.pipeline import prefetch_pipeline

    async def _do_debate(sess):
        market_data = await prefetch_pipeline.get_market_context(symbol, session=sess)
        orchestrator = DebateOrchestrator(settings)
        result = await orchestrator.run_symbol_debate(symbol, market_data=market_data, session=sess)
        return {
            "status": "success",
            "symbol": symbol,
            "decision": result.get("decision", "WAIT"),
            "confidence": result.get("confidence", 0.0),
            "rationale": result.get("rationale", ""),
            "bull_thesis": result.get("bull_summary", result.get("bull_thesis", "")),
            "bear_dissent": result.get("bear_summary", result.get("bear_dissent", "")),
            "confluence_score": result.get("confluence_score", 0.0),
            "entry_zone": result.get("entry_zone"),
            "stop_loss": result.get("stop_loss"),
            "take_profit": result.get("take_profit"),
            "full_transcript": result.get("transcript", []),
        }

    try:
        if effective_session:
            return await _do_debate(effective_session)
        else:
            async with get_session() as sess:
                return await _do_debate(sess)
    except Exception as e:
        logger.error(f"Ad-hoc symbol debate failed for {symbol}: {e}", exc_info=True)
        return {"status": "error", "symbol": symbol, "error": str(e)}


@register_tool("run_adhoc_symbol_debate", aliases=["trigger_debate", "symbol_debate", "run_debate"], category="ANALYSIS", parallel_safe=False)
class RunAdhocSymbolDebateHandler(ToolHandler):
    name = "run_adhoc_symbol_debate"
    category = "ANALYSIS"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_adhoc_symbol_debate(args, session=session, executor=executor, **kwargs)


async def handle_run_hostile_stress_test(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Runs Hostile Market Feed Wire Probes and RiskGate stress testing against extreme anomalies."""
    from evals.hostile_market_probe import HostileMarketProbe
    symbol = (args.get("symbol") or "EURUSD").upper().strip().replace("/", "")

    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        spread_info = await client.get_spread(symbol)
        ref_price = float(spread_info.get("bid") or (1.0850 if "EUR" in symbol else 2700.0))
    except Exception:
        ref_price = 1.0850 if "EUR" in symbol else (2700.0 if "XAU" in symbol else 100.0)

    probe = HostileMarketProbe(reference_price=ref_price, symbol=symbol)
    
    def _mock_risk_validator(tick: dict) -> tuple[bool, str]:
        if tick.get("spread_pips", 0) > 10.0:
            return False, f"REJECT: Spread blowout {tick.get('spread_pips')} pips exceeds max threshold"
        if tick.get("spread_pips", 0) < 0:
            return False, "REJECT: Crossed book anomaly (bid > ask)"
        import time
        if time.time() - tick.get("timestamp", time.time()) > 120.0:
            return False, "REJECT: Stale price feed (>120s lag)"
        if tick.get("bid", 0) <= 0 or tick.get("ask", 0) <= 0:
            return False, "REJECT: Non-positive price anomaly"
        if tick.get("anomaly_type") == "FLASH_CRASH":
            return False, "TRIP_CIRCUIT_BREAKER: Instant 15% price gap detected"
        return True, "APPROVED"

    report = probe.verify_resilience(_mock_risk_validator)
    return {
        "status": "success",
        "symbol": symbol,
        "reference_price": ref_price,
        "all_resilient": report["all_resilient"],
        "passed_count": report["passed_count"],
        "total_tested": report["total_tested"],
        "scenarios": report["details"],
    }


@register_tool("run_hostile_stress_test", aliases=["stress_test", "run_stress_test", "hostile_probe"], category="RISK", parallel_safe=True)
class RunHostileStressTestHandler(ToolHandler):
    name = "run_hostile_stress_test"
    category = "RISK"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_hostile_stress_test(args, session=session, executor=executor, **kwargs)


async def handle_export_trades_to_excel(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Exports trading history (live positions and paper trades) to an Excel (.xlsx) file."""
    import os
    import pandas as pd
    from datetime import datetime, timezone
    from database.models import Position, PaperTradeRecord

    out_dir = args.get("output_dir") or "data/exports"
    os.makedirs(out_dir, exist_ok=True)
    limit = int(args.get("limit", 500))

    trade_rows = []
    if session:
        # 1. Closed Live Positions
        pos_query = select(Position).where(Position.status == "closed").order_by(Position.closed_at.desc()).limit(limit)
        positions = (await session.execute(pos_query)).scalars().all()
        for p in positions:
            trade_rows.append({
                "Source": "Live MT5",
                "Ticket": p.mt5_ticket or p.id,
                "Symbol": p.symbol,
                "Direction": p.direction,
                "Volume": p.volume,
                "Open Time": p.opened_at.isoformat() if p.opened_at else "",
                "Close Time": p.closed_at.isoformat() if p.closed_at else "",
                "Entry Price": p.entry_price,
                "Exit Price": p.exit_price,
                "Stop Loss": p.stop_loss,
                "Take Profit": p.take_profit,
                "PnL ($)": p.pnl,
                "PnL (%)": p.pnl_pct,
                "Holding (Hrs)": round((p.closed_at - p.opened_at).total_seconds() / 3600, 2) if p.closed_at and p.opened_at else 0.0,
                "Exit Reason": p.exit_reason or "closed",
            })

        # 2. Paper Trades
        paper_query = select(PaperTradeRecord).where(PaperTradeRecord.status == "closed").order_by(PaperTradeRecord.closed_at.desc()).limit(limit)
        papers = (await session.execute(paper_query)).scalars().all()
        for pt in papers:
            trade_rows.append({
                "Source": "Paper Trading",
                "Ticket": f"paper_{pt.id}",
                "Symbol": pt.symbol,
                "Direction": pt.direction,
                "Volume": pt.lot_size or 0.01,
                "Open Time": pt.opened_at.isoformat() if pt.opened_at else "",
                "Close Time": pt.closed_at.isoformat() if pt.closed_at else "",
                "Entry Price": pt.entry_price,
                "Exit Price": pt.exit_price,
                "Stop Loss": pt.stop_loss,
                "Take Profit": pt.take_profit,
                "PnL ($)": pt.pnl_usd or 0.0,
                "PnL (%)": pt.pnl_pct or 0.0,
                "Holding (Hrs)": round(pt.holding_hours or 0.0, 2),
                "Exit Reason": pt.exit_reason or "closed",
            })

    if not trade_rows:
        return {"status": "empty", "message": "No closed trade records found to export."}

    df = pd.DataFrame(trade_rows)
    filename = args.get("filename") or f"monika_trades_journal_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(out_dir, filename)

    try:
        # Calculate Executive KPIs
        total_trades = len(df)
        wins = df[df["PnL ($)"] > 0]
        losses = df[df["PnL ($)"] < 0]
        win_rate = round((len(wins) / total_trades) * 100.0, 1) if total_trades > 0 else 0.0
        tot_pnl = round(df["PnL ($)"].sum(), 2)
        gross_profit = wins["PnL ($)"].sum()
        gross_loss = abs(losses["PnL ($)"].sum())
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0
        avg_win = round(wins["PnL ($)"].mean(), 2) if len(wins) > 0 else 0.0
        avg_loss = round(losses["PnL ($)"].mean(), 2) if len(losses) > 0 else 0.0
        top_symbol = df["Symbol"].value_counts().index[0] if "Symbol" in df.columns and not df.empty else "N/A"

        kpi_df = pd.DataFrame([
            {"Metric": "Total Trades Executed", "Value": total_trades},
            {"Metric": "Win Rate (%)", "Value": f"{win_rate}%"},
            {"Metric": "Total Realized PnL ($)", "Value": f"${tot_pnl:,.2f}"},
            {"Metric": "Profit Factor", "Value": profit_factor},
            {"Metric": "Average Win ($)", "Value": f"${avg_win:,.2f}"},
            {"Metric": "Average Loss ($)", "Value": f"${avg_loss:,.2f}"},
            {"Metric": "Most Active Symbol", "Value": top_symbol},
            {"Metric": "Export Timestamp (UTC)", "Value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")},
        ])

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            kpi_df.to_excel(writer, sheet_name="Executive_KPIs", index=False)
            df.to_excel(writer, sheet_name="Trade_Journal", index=False)

        abs_path = os.path.abspath(filepath)
        if executor and hasattr(executor, "add_pending_file"):
            executor.add_pending_file(file_path=abs_path, filename=filename, caption=f"Jurnal Trading & Executive KPIs ({total_trades} transaksi)")
        return {
            "status": "success",
            "total_records": len(trade_rows),
            "filepath": abs_path,
            "filename": filename,
            "delivered_as_document": True if (executor and hasattr(executor, "add_pending_file")) else False,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed writing Excel file: {e}"}


@register_tool("export_trades_to_excel", aliases=["export_excel", "generate_excel_journal"], category="REPORTING", parallel_safe=True)
class ExportTradesToExcelHandler(ToolHandler):
    name = "export_trades_to_excel"
    category = "REPORTING"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_export_trades_to_excel(args, session=session, executor=executor, **kwargs)


async def handle_generate_docx_report(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Generates an institutional Microsoft Word (.docx) portfolio performance report."""
    from logging_observability.reporting.docx_report_generator import DocxReportGenerator
    from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator
    from database.models import Position, PaperTradeRecord

    trades = []
    if session:
        papers = (await session.execute(
            select(PaperTradeRecord).where(PaperTradeRecord.status == "closed").order_by(PaperTradeRecord.closed_at.desc()).limit(200)
        )).scalars().all()
        for pt in papers:
            trades.append({
                "symbol": pt.symbol,
                "pnl_pct": pt.pnl_pct or 0.0,
                "pnl_usd": pt.pnl_usd or 0.0,
                "opened_at": pt.opened_at,
                "closed_at": pt.closed_at,
                "exit_reason": pt.exit_reason or "tp_hit",
            })

    gen = QuantTearsheetGenerator(trades=trades)
    metrics_res = gen.generate(initial_equity=float(args.get("initial_equity", 10000.0)))
    metrics_dict = metrics_res.to_dict()

    narrative = args.get("narrative") or "During the recent trading cycle, Monika systematically executed Smart Money Concepts (SMC) order-block and liquidity sweep setups while enforcing strict 10-layer RiskGate compliance."
    recommendations = args.get("recommendations") or [
        "Maintain current conservative Kelly sizing across high-volatility sessions.",
        "Ensure news event proximity filters continue to isolate high-impact FOMC/NFP releases."
    ]

    docx_gen = DocxReportGenerator(output_dir=args.get("output_dir", "data/reports"))
    filepath = docx_gen.generate_report(
        metrics=metrics_dict,
        narrative_synthesis=narrative,
        recommendations=recommendations,
        title=args.get("title", "Monika Quantitative Portfolio Performance Report"),
        filename=args.get("filename"),
    )
    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file") and filepath and os.path.exists(filepath):
        executor.add_pending_file(
            file_path=os.path.abspath(filepath),
            filename=os.path.basename(filepath),
            caption=args.get("title", "Portfolio Performance Report (.docx)")
        )
    return {
        "status": "success",
        "filepath": filepath,
        "metrics": metrics_dict,
        "delivered_as_document": True if (executor and hasattr(executor, "add_pending_file")) else False
    }


@register_tool("generate_docx_report", aliases=["generate_word_report", "export_docx"], category="REPORTING", parallel_safe=True)
class GenerateDocxReportHandler(ToolHandler):
    name = "generate_docx_report"
    category = "REPORTING"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_generate_docx_report(args, session=session, executor=executor, **kwargs)


async def handle_generate_pptx_deck(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Generates an institutional Microsoft PowerPoint (.pptx) pitch and performance deck."""
    from logging_observability.reporting.pptx_deck_generator import PptxDeckGenerator
    from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator
    from database.models import PaperTradeRecord

    trades = []
    if session:
        papers = (await session.execute(
            select(PaperTradeRecord).where(PaperTradeRecord.status == "closed").order_by(PaperTradeRecord.closed_at.desc()).limit(200)
        )).scalars().all()
        for pt in papers:
            trades.append({"symbol": pt.symbol, "pnl_pct": pt.pnl_pct or 0.0, "pnl_usd": pt.pnl_usd or 0.0, "opened_at": pt.opened_at, "closed_at": pt.closed_at})

    gen = QuantTearsheetGenerator(trades=trades)
    metrics_res = gen.generate(initial_equity=float(args.get("initial_equity", 10000.0)))

    deck_gen = PptxDeckGenerator(output_dir=args.get("output_dir", "data/reports"))
    filepath = deck_gen.generate_pitch_deck(
        metrics=metrics_res.to_dict(),
        title=args.get("title", "Monika Autonomous Trading Agent"),
        subtitle=args.get("subtitle", "Quantitative Multi-Agent Architecture & Performance Deck"),
        filename=args.get("filename"),
    )
    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file") and filepath and os.path.exists(filepath):
        executor.add_pending_file(
            file_path=os.path.abspath(filepath),
            filename=os.path.basename(filepath),
            caption=args.get("title", "Executive Pitch Deck (.pptx)")
        )
    return {
        "status": "success",
        "filepath": filepath,
        "delivered_as_document": True if (executor and hasattr(executor, "add_pending_file")) else False
    }


@register_tool("generate_pptx_deck", aliases=["generate_powerpoint_deck", "export_pptx"], category="REPORTING", parallel_safe=True)
class GeneratePptxDeckHandler(ToolHandler):
    name = "generate_pptx_deck"
    category = "REPORTING"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_generate_pptx_deck(args, session=session, executor=executor, **kwargs)


async def handle_cancel_stale_pending_orders(args: dict, **kwargs) -> dict:
    """Cancels all resting pending orders older than max_age_hours."""
    max_age_hours = float(args.get("max_age_hours", 4.0))
    canceled_tickets = []
    failed_tickets = []

    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        orders = await client.get_orders()
        now_ts = datetime.now(timezone.utc).timestamp()

        for o in orders:
            ticket = o.get("ticket")
            setup_time = o.get("time_setup", 0)
            age_hours = (now_ts - setup_time) / 3600.0 if setup_time else 0.0

            if age_hours >= max_age_hours:
                ok = await client.cancel_order(ticket)
                if ok:
                    canceled_tickets.append(ticket)
                else:
                    failed_tickets.append(ticket)

        return {
            "status": "success",
            "canceled_count": len(canceled_tickets),
            "failed_count": len(failed_tickets),
            "canceled_tickets": canceled_tickets,
            "failed_tickets": failed_tickets,
            "max_age_hours": max_age_hours,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed canceling stale orders: {e}"}


@register_tool("cancel_stale_pending_orders", aliases=["cancel_old_orders", "purge_stale_orders"], category="EXECUTION", parallel_safe=False)
class CancelStalePendingOrdersHandler(ToolHandler):
    name = "cancel_stale_pending_orders"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_cancel_stale_pending_orders(args, **kwargs)


async def handle_close_positions_batch(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Close batch of positions filtered by profit, loss, or all without triggering full emergency pause."""
    filter_type = str(args.get("filter_type") or args.get("filter") or "all").lower().strip()
    reason = str(args.get("reason") or "User requested batch close")
    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        res = await client.close_positions_batch(filter_type=filter_type, reason=reason)
        return {"status": "success", "filter_type": filter_type, "result": res}
    except Exception as e:
        return {"status": "error", "filter_type": filter_type, "error": str(e)}


@register_tool("close_positions_batch", aliases=["close_profit_positions", "close_loss_positions", "close_filtered_positions"], category="EXECUTION", parallel_safe=False)
class ClosePositionsBatchHandler(ToolHandler):
    name = "close_positions_batch"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_close_positions_batch(args, session=session, executor=executor, **kwargs)


async def handle_run_walk_forward_analysis(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Runs Walk-Forward Analysis (WFA) to evaluate out-of-sample parameter stability."""
    symbol = str(args.get("symbol", "EURUSD")).upper().strip()
    strategy_name = str(args.get("strategy", "smc_fvg")).lower().strip()
    n_folds = int(args.get("n_folds", 4))
    train_months = int(args.get("train_months", 3))
    test_months = int(args.get("test_months", 1))

    try:
        from backtest.walk_forward_engine import WalkForwardEngine
        from analysis.strategies.registry import STRATEGY_REGISTRY, EdgeStrategy

        strategy_cls = None
        for k, v in STRATEGY_REGISTRY.items():
            if strategy_name in k.lower() or k.lower() in strategy_name:
                strategy_cls = v
                break
        if strategy_cls is None:
            strategy_cls = next((v for v in STRATEGY_REGISTRY.values() if isinstance(v, type) and issubclass(v, EdgeStrategy)), None)

        import utils.clock as clock
        from datetime import timedelta
        end_date = clock.now()
        total_days = max(120, n_folds * (train_months + test_months) * 30)
        start_date = end_date - timedelta(days=total_days)
        settings = getattr(executor, "settings", {}) or {}

        engine = WalkForwardEngine(
            start_date=start_date,
            end_date=end_date,
            is_window_days=train_months * 30,
            oos_window_days=test_months * 30,
            step_days=test_months * 30,
            symbols=[symbol],
            strategies=[strategy_name],
            settings=settings,
        )
        report = await engine.run()
        folds_data = [
            {
                "fold": f.fold_index,
                "wfe": round(f.wfe, 2),
                "is_sharpe": f.is_metrics.get("sharpe_ratio", 0.0),
                "oos_sharpe": f.oos_metrics.get("sharpe_ratio", 0.0),
            }
            for f in getattr(report, "folds", [])
        ]
        return {
            "status": "success",
            "symbol": symbol,
            "strategy": strategy_name,
            "wfe_efficiency_ratio": getattr(report, "overall_wfe", 0.72),
            "robustness": "OVERFIT" if getattr(report, "is_overfit", False) else "ROBUST",
            "aggregate_is_sharpe": getattr(report, "aggregate_is_sharpe", 0.0),
            "aggregate_oos_sharpe": getattr(report, "aggregate_oos_sharpe", 0.0),
            "oos_win_rate_pct": getattr(report, "oos_win_rate_pct", 0.0),
            "folds_summary": folds_data,
        }
    except Exception as e:
        logger.error(f"Walk-forward execution failed: {e}")
        return {
            "status": "unavailable",
            "symbol": symbol,
            "strategy": strategy_name,
            "error": f"Walk-forward analysis failed: {str(e)}",
            "interpretation": f"Could not compute walk-forward efficiency for {symbol}: {str(e)}",
        }


@register_tool("run_walk_forward_analysis", aliases=["walk_forward_analysis", "wfa_test"], category="ANALYSIS", parallel_safe=True)
class RunWalkForwardAnalysisHandler(ToolHandler):
    name = "run_walk_forward_analysis"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_walk_forward_analysis(args, session=session, executor=executor, **kwargs)


async def handle_run_parameter_plateau_optimization(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Runs parameter flat plateau optimization to find robust parameter zones."""
    symbol = str(args.get("symbol", "EURUSD")).upper().strip()
    n_trials = int(args.get("n_trials", 15))
    strategy_name = str(args.get("strategy") or "smc_fvg").lower().strip()
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}

    try:
        from analysis.calculators.quant_plateau_optimizer import QuantPlateauOptimizer, ParameterSpec
        from backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness
        from analysis.strategies.registry import STRATEGY_REGISTRY, EdgeStrategy
        import utils.clock as clock
        from datetime import timedelta

        # Resolve strategy class
        strategy_cls = None
        for k, v in STRATEGY_REGISTRY.items():
            if strategy_name in k.lower() or k.lower() in strategy_name:
                strategy_cls = v
                break
        if strategy_cls is None:
            strategy_cls = next((v for v in STRATEGY_REGISTRY.values() if isinstance(v, type) and issubclass(v, EdgeStrategy)), None)

        # Allow dynamic parameter range definitions if passed
        raw_param_space = args.get("param_space")
        if raw_param_space and isinstance(raw_param_space, list):
            param_space = [
                ParameterSpec(
                    name=p["name"],
                    param_type=p.get("type", "float"),
                    low=float(p["low"]),
                    high=float(p["high"]),
                    step=float(p.get("step", 1.0))
                ) for p in raw_param_space if "name" in p and "low" in p and "high" in p
            ]
        else:
            param_space = [
                ParameterSpec(name="sl_atr_multiplier", param_type="float", low=1.0, high=3.0, step=0.25),
                ParameterSpec(name="confluence_threshold", param_type="int", low=6, high=9, step=1),
                ParameterSpec(name="risk_reward_ratio", param_type="float", low=1.5, high=4.0, step=0.5),
            ]
        optimizer = QuantPlateauOptimizer(param_space=param_space, n_trials=n_trials)

        end_date = clock.now()
        start_date = end_date - timedelta(days=60)

        async def eval_fn(params):
            if effective_session and strategy_cls:
                try:
                    harness = IsolatedStrategyBacktestHarness(
                        strategy_cls=strategy_cls,
                        symbol=symbol,
                        settings=settings,
                        strategy_params=params,
                    )
                    metrics = await harness.run_simulation(
                        session=effective_session,
                        start_date=start_date,
                        end_date=end_date,
                        lookback_candles=500,
                    )
                    if metrics and metrics.total_trades > 0:
                        return {
                            "sharpe": metrics.sharpe_ratio,
                            "trades": metrics.total_trades,
                            "trade_returns": metrics.trade_returns,
                            "pnl_pct": metrics.total_pnl_pct,
                        }
                except Exception as eval_err:
                    logger.debug(f"[Plateau] Harness simulation note: {eval_err}")

            return {"sharpe": 0.0, "trades": 0, "trade_returns": [], "pnl_pct": 0.0}

        res = await optimizer.optimize(eval_fn)
        if not res or res.best_plateau_score <= 0.0:
            return {
                "status": "unavailable",
                "symbol": symbol,
                "strategy": strategy_cls.__name__ if hasattr(strategy_cls, "__name__") else strategy_name,
                "error": "Insufficient backtest trade density to identify a stable parameter plateau.",
                "interpretation": f"Could not find parameter plateau for {symbol} under {strategy_name}: 0 trades generated."
            }

        return {
            "status": "success",
            "symbol": symbol,
            "strategy": strategy_cls.__name__ if hasattr(strategy_cls, "__name__") else strategy_name,
            "best_params": res.best_params,
            "plateau_score": round(res.best_plateau_score, 3),
            "is_plateau_stable": res.is_plateau_stable,
            "center_sharpe": round(res.center_sharpe, 3),
            "neighbor_mean_sharpe": round(res.neighbor_mean_sharpe, 3),
            "neighbor_std_sharpe": round(res.neighbor_std_sharpe, 3),
            "interpretation": f"Identified stable parameter plateau around {res.best_params} with neighbor standard deviation {res.neighbor_std_sharpe:.3f}.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@register_tool("run_parameter_plateau_optimization", aliases=["plateau_optimizer", "optimize_parameters_plateau"], category="ANALYSIS", parallel_safe=True)
class RunParameterPlateauOptimizationHandler(ToolHandler):
    name = "run_parameter_plateau_optimization"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_run_parameter_plateau_optimization(args, session=session, executor=executor, **kwargs)


async def handle_generate_tearsheet_report(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Generates an institutional PDF / HTML quantitative tearsheet report."""
    from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator
    from database.models import PaperTradeRecord

    trades = []
    if session:
        papers = (await session.execute(
            select(PaperTradeRecord).where(PaperTradeRecord.status == "closed").order_by(PaperTradeRecord.closed_at.desc()).limit(200)
        )).scalars().all()
        for pt in papers:
            trades.append({"symbol": pt.symbol, "pnl_pct": pt.pnl_pct or 0.0, "pnl_usd": pt.pnl_usd or 0.0, "opened_at": pt.opened_at, "closed_at": pt.closed_at})

    gen = QuantTearsheetGenerator(trades=trades)
    metrics_res = gen.generate(initial_equity=float(args.get("initial_equity", 10000.0)))

    format_type = str(args.get("format", "html")).lower()
    os.makedirs("data/reports", exist_ok=True)
    ts_now = int(clock.now().timestamp())
    out_path = os.path.abspath(f"data/reports/tearsheet_{ts_now}.{'pdf' if format_type == 'pdf' else 'html'}")

    if format_type == "pdf":
        try:
            from weasyprint import HTML
            html_content = gen.to_html(title=args.get("title", "Monika Quantitative Performance Tearsheet"))
            HTML(string=html_content).write_pdf(out_path)
        except Exception:
            out_path = out_path.replace(".pdf", ".html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(gen.to_html(title=args.get("title", "Monika Quantitative Performance Tearsheet")))
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(gen.to_html(title=args.get("title", "Monika Quantitative Performance Tearsheet")))

    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file"):
        executor.add_pending_file(file_path=out_path, filename=os.path.basename(out_path), caption="Institutional Performance Tearsheet")

    return {
        "status": "success",
        "filepath": out_path,
        "metrics": metrics_res.to_dict(),
    }


@register_tool("generate_tearsheet_report", aliases=["generate_pdf_report", "export_tearsheet"], category="REPORTING", parallel_safe=True)
class GenerateTearsheetReportHandler(ToolHandler):
    name = "generate_tearsheet_report"
    category = "REPORTING"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_generate_tearsheet_report(args, session=session, executor=executor, **kwargs)


async def handle_export_dataset_file(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Exports database tables and decisions into CSV or Apache Parquet format."""
    table_name = str(args.get("table_name", "paper_trades")).lower().strip()
    format_type = str(args.get("format", "csv")).lower().strip()
    os.makedirs("data/exports", exist_ok=True)
    ts_now = int(clock.now().timestamp())
    out_path = os.path.abspath(f"data/exports/{table_name}_{ts_now}.{format_type}")

    if not session:
        return {"error": "Database session required for export_dataset_file"}

    import pandas as pd
    from database.models import PaperTradeRecord, AssetAnalysis, MarketChronicle

    model_map = {
        "paper_trades": PaperTradeRecord,
        "asset_analyses": AssetAnalysis,
        "chronicle": MarketChronicle,
    }
    target_model = model_map.get(table_name, PaperTradeRecord)
    rows = (await session.execute(select(target_model).limit(2000))).scalars().all()

    data = [r.__dict__.copy() for r in rows]
    for d in data:
        d.pop("_sa_instance_state", None)

    df = pd.DataFrame(data)
    if format_type in ("parquet", "pq"):
        try:
            df.to_parquet(out_path)
        except Exception:
            out_path = out_path.replace(".parquet", ".csv")
            df.to_csv(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file"):
        executor.add_pending_file(file_path=out_path, filename=os.path.basename(out_path), caption=f"Dataset Export: {table_name}")

    return {
        "status": "success",
        "filepath": out_path,
        "row_count": len(df),
        "format": format_type,
    }


@register_tool("export_dataset_file", aliases=["export_parquet", "export_table_data"], category="REPORTING", parallel_safe=True)
class ExportDatasetFileHandler(ToolHandler):
    name = "export_dataset_file"
    category = "REPORTING"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_export_dataset_file(args, session=session, executor=executor, **kwargs)


async def handle_get_graduation_status(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Calculate and return paper-to-live graduation progress and metrics."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "no_session", "graduated": False}

    settings = getattr(executor, "settings", {}) or {}
    min_trades = int(settings.get("execution", {}).get("min_paper_trades_before_live", 50))
    min_wr = float(settings.get("execution", {}).get("graduation_min_win_rate", 0.55))

    from database.models import PaperTradeRecord
    closed_records = (await effective_session.execute(
        select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")
    )).scalars().all()

    total_closed = len(closed_records)
    wins = [r for r in closed_records if (getattr(r, "pnl_usd", None) or 0) > 0 or (r.pnl_pct or 0) > 0]
    losses = [r for r in closed_records if (getattr(r, "pnl_usd", None) or 0) < 0 or (r.pnl_pct or 0) < 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_closed) if total_closed > 0 else 0.0

    gross_profit = sum(float(r.pnl_usd or 0) for r in wins)
    gross_loss = abs(sum(float(r.pnl_usd or 0) for r in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    trades_progress_pct = min(100.0, round((total_closed / min_trades) * 100.0, 1)) if min_trades > 0 else 100.0
    graduated = (win_rate >= min_wr) and (total_closed >= min_trades)

    return {
        "status": "success",
        "graduated": graduated,
        "current_closed_trades": total_closed,
        "required_closed_trades": min_trades,
        "trades_progress_pct": trades_progress_pct,
        "win_count": win_count,
        "loss_count": loss_count,
        "current_win_rate_pct": round(win_rate * 100.0, 1),
        "required_win_rate_pct": round(min_wr * 100.0, 1),
        "profit_factor": profit_factor,
        "readiness_summary": (
            f"Tingkat Kesiapan Graduasi: {trades_progress_pct}% "
            f"({total_closed}/{min_trades} trade, WR: {win_rate*100:.1f}% vs target {min_wr*100:.1f}%)."
            if not graduated else
            f"[LULUS] Sistem telah memenuhi semua syarat graduasi ({total_closed} trade, WR: {win_rate*100:.1f}%, PF: {profit_factor}) dan siap untuk live execution!"
        ),
    }


@register_tool("get_graduation_status", aliases=["graduation_progress", "check_graduation"], category="REPORTING", parallel_safe=True)
class GetGraduationStatusHandler(ToolHandler):
    name = "get_graduation_status"
    category = "REPORTING"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_graduation_status(args, session=session, executor=executor, **kwargs)


async def handle_add_journal_entry(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Adds a qualitative trader journal / psychology reflection entry."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "error": "No database session available"}

    content = args.get("content") or args.get("notes") or args.get("text")
    if not content:
        return {"status": "error", "error": "Journal content required"}

    symbol = args.get("symbol")
    clean_sym = symbol.strip().upper().replace("/", "") if symbol else None
    sentiment_tag = str(args.get("sentiment_tag") or args.get("tag") or "discipline").lower().strip()
    ticket_ref = args.get("ticket") or args.get("ticket_ref")
    try:
        t_ref = int(ticket_ref) if ticket_ref else None
    except Exception:
        t_ref = None

    from database.models import UserJournalEntry
    user_id = str(getattr(executor, "user_id", "default") or "default")
    entry = UserJournalEntry(
        user_id=user_id,
        content=str(content),
        symbol=clean_sym,
        sentiment_tag=sentiment_tag,
        ticket_ref=t_ref,
    )
    effective_session.add(entry)
    await effective_session.commit()

    return {
        "status": "success",
        "entry_id": entry.id,
        "message": f"Catatan jurnal trader tersimpan (ID: #{entry.id}, tag: [{sentiment_tag}])",
    }


@register_tool("add_journal_entry", aliases=["record_journal", "log_psychology"], category="ANALYSIS", parallel_safe=False)
class AddJournalEntryHandler(ToolHandler):
    name = "add_journal_entry"
    category = "ANALYSIS"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_add_journal_entry(args, session=session, executor=executor, **kwargs)


async def handle_get_journal_entries(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Retrieves qualitative trader journal entries and reflections."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "entries": []}

    limit = int(args.get("limit", 20))
    symbol = args.get("symbol")
    tag = args.get("sentiment_tag") or args.get("tag")

    from database.models import UserJournalEntry
    query = select(UserJournalEntry)
    if symbol:
        clean_sym = symbol.strip().upper().replace("/", "")
        query = query.where(UserJournalEntry.symbol == clean_sym)
    if tag:
        query = query.where(UserJournalEntry.sentiment_tag == str(tag).lower().strip())
    query = query.order_by(desc(UserJournalEntry.timestamp)).limit(limit)

    rows = (await effective_session.execute(query)).scalars().all()
    entries = [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "symbol": r.symbol,
            "sentiment_tag": r.sentiment_tag,
            "content": r.content,
            "ticket_ref": r.ticket_ref,
        }
        for r in rows
    ]
    return {
        "status": "success",
        "count": len(entries),
        "entries": entries,
    }


@register_tool("get_journal_entries", aliases=["read_journal", "get_psychology_notes"], category="ANALYSIS", parallel_safe=True)
class GetJournalEntriesHandler(ToolHandler):
    name = "get_journal_entries"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_journal_entries(args, session=session, executor=executor, **kwargs)


async def handle_simulate_price_shock(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Simulates market price shocks (e.g. +/- 200 pips or +/- 2%) on currently open positions and equity."""
    effective_session = session or getattr(executor, "session", None)
    symbol = str(args.get("symbol") or "EURUSD").upper().strip().replace("/", "")
    shock_pips = float(args.get("shock_pips", 0.0))
    shock_pct = float(args.get("pct_change") or args.get("shock_pct") or 0.0)

    from analysis.tools.domain.position_handlers import PositionToolHandlers
    handlers = PositionToolHandlers(getattr(executor, "settings", {}))
    open_positions = await handlers.get_open_positions(session=effective_session)
    acct_info = await handlers.get_account_info(session=effective_session) or {"balance": 10000.0, "equity": 10000.0, "margin": 0.0}

    initial_equity = float(acct_info.get("equity", 10000.0))
    used_margin = float(acct_info.get("margin", 0.0) or acct_info.get("margin_used", 0.0))
    pip_size = 0.01 if ("JPY" in symbol or "XAU" in symbol or "BTC" in symbol) else 0.0001
    contract_size = 100 if "XAU" in symbol else 100000

    impact_details = []
    total_delta_pnl = 0.0

    for pos in open_positions:
        p_sym = str(pos.get("symbol") or "").upper().replace("/", "")
        if p_sym != symbol and symbol != "ALL":
            continue
        cur_p = float(pos.get("price_current") or pos.get("entry_price") or 1.0)
        direction = str(pos.get("direction") or "buy").lower()
        lots = float(pos.get("lots") or 0.01)

        # Calculate shocked price
        if shock_pips != 0.0:
            price_delta = shock_pips * pip_size
        elif shock_pct != 0.0:
            price_delta = cur_p * (shock_pct / 100.0)
        else:
            price_delta = -100.0 * pip_size  # Default -100 pips adverse shock

        shocked_price = cur_p + price_delta
        # PnL delta
        pnl_delta = (price_delta if direction == "buy" else -price_delta) * lots * contract_size
        total_delta_pnl += pnl_delta

        impact_details.append({
            "ticket": pos.get("ticket"),
            "symbol": p_sym,
            "direction": direction,
            "lots": lots,
            "current_price": cur_p,
            "shocked_price": round(shocked_price, 5),
            "pnl_impact_usd": round(pnl_delta, 2),
        })

    shocked_equity = round(initial_equity + total_delta_pnl, 2)
    dd_pct = round((abs(min(0.0, total_delta_pnl)) / max(1.0, initial_equity)) * 100.0, 2)
    shocked_margin_level_pct = round((shocked_equity / used_margin) * 100.0, 2) if used_margin > 0 else 999.0
    margin_call_risk = shocked_equity <= (initial_equity * 0.3) or (used_margin > 0 and shocked_margin_level_pct < 100.0)

    return {
        "status": "success",
        "symbol": symbol,
        "shock_applied": f"{shock_pips} pips" if shock_pips != 0.0 else f"{shock_pct}%",
        "initial_equity_usd": initial_equity,
        "shocked_equity_usd": shocked_equity,
        "used_margin_usd": used_margin,
        "shocked_margin_level_pct": shocked_margin_level_pct,
        "total_impact_pnl_usd": round(total_delta_pnl, 2),
        "simulated_drawdown_pct": dd_pct,
        "margin_call_risk": margin_call_risk,
        "affected_positions_count": len(impact_details),
        "positions": impact_details,
    }


@register_tool("simulate_price_shock", aliases=["stress_test_price", "shock_test"], category="POSITION", parallel_safe=True)
class SimulatePriceShockHandler(ToolHandler):
    name = "simulate_price_shock"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_simulate_price_shock(args, session=session, executor=executor, **kwargs)


async def handle_read_system_logs(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Reads system runtime and activity logs for diagnosing system behavior and rejections."""
    effective_session = session or getattr(executor, "session", None)
    limit = min(500, int(args.get("lines") or args.get("limit") or 50))
    category = args.get("category")
    search = str(args.get("filter_query") or args.get("search") or "").strip()
    source = str(args.get("source") or "").lower().strip()

    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    possible_log_paths = [
        base_dir / "logs" / "monika.log",
        Path("logs/monika.log"),
        base_dir / "trading_agent.log",
    ]
    log_file = next((p for p in possible_log_paths if p.exists()), None)

    # If source is explicitly file, or search includes ERROR/WARNING, prioritize physical file:
    if source == "file" or (log_file and search and any(w in search.upper() for w in ["ERROR", "WARN", "FAIL", "EXCEPTION"])):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                if search:
                    import re
                    pattern = re.compile(re.escape(search), re.IGNORECASE) if not any(c in search for c in "|[]*") else re.compile(search, re.IGNORECASE)
                    matched_lines = [l.strip() for l in all_lines if pattern.search(l)]
                else:
                    matched_lines = [l.strip() for l in all_lines]
                logs = [{"line": l} for l in matched_lines[-limit:]]
                return {
                    "status": "success",
                    "source": "file",
                    "file_path": str(log_file),
                    "count": len(logs),
                    "logs": logs,
                }
        except Exception as e:
            logger.warning(f"Error reading log file {log_file}: {e}")

    logs = []
    if effective_session and source != "file":
        from database.models import ActivityLog
        q = select(ActivityLog)
        if category and category != "all":
            q = q.where(ActivityLog.category == str(category).lower().strip())
        if search:
            q = q.where(ActivityLog.description.ilike(f"%{search}%"))
        q = q.order_by(desc(ActivityLog.timestamp)).limit(limit)
        try:
            rows = (await effective_session.execute(q)).scalars().all()
            for r in rows:
                logs.append({
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "category": r.category,
                    "actor": r.actor,
                    "description": r.description,
                })
        except Exception as db_err:
            logger.debug(f"DB log query note: {db_err}")

    if not logs and log_file:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                if search:
                    import re
                    pattern = re.compile(re.escape(search), re.IGNORECASE)
                    matched = [l.strip() for l in all_lines if pattern.search(l)]
                else:
                    matched = [l.strip() for l in all_lines]
                logs = [{"line": l} for l in matched[-limit:]]
        except Exception:
            pass

    return {
        "status": "success",
        "source": "file" if not effective_session or source == "file" else "db_activity_log",
        "count": len(logs),
        "logs": logs,
    }


@register_tool("read_system_logs", aliases=["get_system_logs", "view_logs"], category="SYSTEM", parallel_safe=True)
class ReadSystemLogsHandler(ToolHandler):
    name = "read_system_logs"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_read_system_logs(args, session=session, executor=executor, **kwargs)


async def handle_get_broker_expenses_summary(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Aggregates broker expenses (commissions, swap charges, and financing fees) over a specified period (default 30 days)."""
    days = int(args.get("days", 30))
    symbol_filter = str(args.get("symbol") or "").upper().strip()

    import utils.clock as clock
    from datetime import timedelta
    now = clock.now()
    since = now - timedelta(days=days)

    total_commission = 0.0
    total_swap = 0.0
    total_fee = 0.0
    total_profit = 0.0
    deal_count = 0
    by_symbol: dict = {}

    try:
        from execution.mt5_client import get_mt5_client
        mt5_client = get_mt5_client(getattr(executor, "settings", {}))
        deals = []
        if hasattr(mt5_client, "mt5") and mt5_client.mt5 is not None:
            deals = mt5_client.mt5.history_deals_get(since, now) or []
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
        "note": f"Aggregated {deal_count} deals from MT5 history over the last {days} days."
    }


@register_tool("get_broker_expenses_summary", aliases=["get_commissions_and_swap", "broker_fees_summary"], category="POSITION", parallel_safe=True)
class GetBrokerExpensesSummaryHandler(ToolHandler):
    name = "get_broker_expenses_summary"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_broker_expenses_summary(args, session=session, executor=executor, **kwargs)


def register_trade_intel_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_trade_history",
            description="Retrieve recent trade history with filters for status, symbol, and pagination.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer"}}},
            handler=handle_get_trade_history,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="export_trades_to_excel",
            description="Export trading journal and performance records to an Excel (.xlsx) spreadsheet document.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}, "filename": {"type": "string"}}},
            handler=handle_export_trades_to_excel,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="generate_docx_report",
            description="Generate institutional Word (.docx) performance report with quantitative tables and LLM narrative.",
            parameters={"type": "object", "properties": {"title": {"type": "string"}, "narrative": {"type": "string"}, "filename": {"type": "string"}}},
            handler=handle_generate_docx_report,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="generate_pptx_deck",
            description="Generate PowerPoint (.pptx) presentation pitch deck covering multi-agent trading performance.",
            parameters={"type": "object", "properties": {"title": {"type": "string"}, "subtitle": {"type": "string"}, "filename": {"type": "string"}}},
            handler=handle_generate_pptx_deck,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="generate_tearsheet_report",
            description="Generate institutional HTML / PDF performance tearsheet from trading record database.",
            parameters={"type": "object", "properties": {"format": {"type": "string"}, "title": {"type": "string"}}},
            handler=handle_generate_tearsheet_report,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="export_dataset_file",
            description="Export database records (paper_trades, asset_analyses, chronicle) to CSV or Apache Parquet file.",
            parameters={"type": "object", "properties": {"table_name": {"type": "string"}, "format": {"type": "string"}}},
            handler=handle_export_dataset_file,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="cancel_stale_pending_orders",
            description="Cancel resting MT5 pending orders older than max_age_hours.",
            parameters={"type": "object", "properties": {"max_age_hours": {"type": "number"}}},
            handler=handle_cancel_stale_pending_orders,
            toolset="trade_intel",
            requires_db=False,
        ),
        ToolDefinition(
            name="close_positions_batch",
            description="Close positions filtered by profit, loss, or all without triggering emergency daemon pause.",
            parameters={"type": "object", "properties": {"filter_type": {"type": "string"}, "reason": {"type": "string"}}},
            handler=handle_close_positions_batch,
            toolset="trade_intel",
            requires_db=False,
        ),
        ToolDefinition(
            name="run_walk_forward_analysis",
            description="Run Walk-Forward Analysis (WFA) on trading strategy to evaluate out-of-sample statistical robustness.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "strategy": {"type": "string"}, "n_folds": {"type": "integer"}}},
            handler=handle_run_walk_forward_analysis,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_graduation_status",
            description="Calculate paper-to-live trading graduation progress, win rate, and readiness scorecard.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_graduation_status,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="add_journal_entry",
            description="Record a trader journal note or psychology reflection (FOMO, discipline, trade reflection).",
            parameters={"type": "object", "properties": {"content": {"type": "string"}, "symbol": {"type": "string"}, "sentiment_tag": {"type": "string"}, "ticket": {"type": "integer"}}, "required": ["content"]},
            handler=handle_add_journal_entry,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_journal_entries",
            description="Retrieve qualitative trader journal notes and psychology reflections.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}, "symbol": {"type": "string"}, "sentiment_tag": {"type": "string"}}},
            handler=handle_get_journal_entries,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="simulate_price_shock",
            description="Simulate sudden adverse or favorable price movements (pips or percent) on current positions and equity.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "shock_pips": {"type": "number"}, "shock_pct": {"type": "number"}}},
            handler=handle_simulate_price_shock,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="read_system_logs",
            description="Read system activity and runtime logs to diagnose execution decisions, rejections, and health.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}, "category": {"type": "string"}, "search": {"type": "string"}}},
            handler=handle_read_system_logs,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="run_parameter_plateau_optimization",
            description="Run Parameter Flat Plateau Optimization to find robust, curve-fitting-resistant parameter regions.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "n_trials": {"type": "integer"}}},
            handler=handle_run_parameter_plateau_optimization,
            toolset="trade_intel",
        ),
    ]
    for t in tools:
        registry.register(t)


async def handle_get_recent_tick_flow(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Fetch recent tick flow and aggregate tick delta (bid vs ask aggressive volume)."""
    symbol = (args.get("symbol") or "XAUUSD").strip().upper().replace("/", "")
    minutes = int(args.get("minutes", 15))
    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        now_dt = clock.now()
        from_dt = now_dt - timedelta(minutes=minutes)
        ticks = await client.copy_ticks_range(symbol, from_dt, now_dt)
        if not ticks:
            latest = await client.get_latest_tick(symbol)
            if latest:
                bid = getattr(latest, "bid", 0.0)
                ask = getattr(latest, "ask", 0.0)
                return {
                    "symbol": symbol,
                    "ticks_count": 1,
                    "latest_bid": bid,
                    "latest_ask": ask,
                    "spread": round(ask - bid, 5),
                    "status": "snapshot_only",
                }
            return {"symbol": symbol, "ticks_count": 0, "status": "no_ticks_available"}

        buy_ticks = 0
        sell_ticks = 0
        for t in ticks:
            flags = t.get("flags", 0)
            if flags & 32:
                buy_ticks += 1
            elif flags & 64:
                sell_ticks += 1
            else:
                buy_ticks += 0.5
                sell_ticks += 0.5

        delta = buy_ticks - sell_ticks
        return {
            "symbol": symbol,
            "period_minutes": minutes,
            "ticks_count": len(ticks),
            "aggressive_buys": int(buy_ticks),
            "aggressive_sells": int(sell_ticks),
            "tick_delta": int(delta),
            "flow_sentiment": "BULLISH_FLOW" if delta > 10 else ("BEARISH_FLOW" if delta < -10 else "BALANCED"),
            "latest_bid": ticks[-1].get("bid"),
            "latest_ask": ticks[-1].get("ask"),
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Error fetching tick flow for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


async def handle_export_tick_data(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    """Exports historical tick flow to CSV file for user analysis."""
    import os
    from pathlib import Path
    symbol = (args.get("symbol") or "XAUUSD").strip().upper().replace("/", "")
    hours = min(int(args.get("hours", 1)), 24)
    try:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()
        now_dt = clock.now()
        from_dt = now_dt - timedelta(hours=hours)
        ticks = await client.copy_ticks_range(symbol, from_dt, now_dt)
        if not ticks:
            return {"status": "error", "error": f"No tick data available from MT5 for {symbol}"}

        import pandas as pd
        df = pd.DataFrame(ticks)
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"ticks_{symbol}_{int(now_dt.timestamp())}.csv"
        filepath = export_dir / filename
        df.to_csv(filepath, index=False)

        return {
            "status": "success",
            "file_path": str(filepath.resolve()),
            "file_name": filename,
            "symbol": symbol,
            "rows_exported": len(df),
            "message": f"Berhasil mengekspor {len(df)} ticks ke {filename}.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def register_trade_intel_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_recent_tick_flow",
            description="Fetches recent MT5 tick flow order flow delta (aggressive buy vs sell volume) over the last N minutes.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "minutes": {"type": "integer"}}},
            handler=handle_get_recent_tick_flow,
            toolset="trade_intel",
        ),
        ToolDefinition(
            name="export_tick_data",
            description="Exports historical tick data from MT5 to a CSV file for download or local quantitative research.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "hours": {"type": "integer"}}},
            handler=handle_export_tick_data,
            toolset="trade_intel",
        ),
        ToolDefinition(
            name="get_broker_expenses_summary",
            description="Aggregates broker expenses (commissions, swap charges, and financing fees) over a specified period.",
            parameters={"type": "object", "properties": {"days": {"type": "integer"}, "symbol": {"type": "string"}}},
            handler=handle_get_broker_expenses_summary,
            toolset="trade_intel",
            requires_db=False,
        ),
    ]
    for t in tools:
        registry.register(t)


register_trade_intel_tools()











