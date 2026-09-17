# ==============================================================================
# File: analysis/tools/handlers/trade_intel.py
# ==============================================================================

"""
Trade intelligence and history tool handlers.
Direct execution without circular trampolines.
"""

import json
from typing import Any, Dict, Optional, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AssetAnalysis, PaperTradeRecord, TradeTrigger, TelegramConversation
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


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
        }
        for r in rows
    ]
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

    if not record:
        return {"status": "not_found", "trade_id": tid}

    return {
        "id": record.id,
        "symbol": record.symbol,
        "direction": record.direction,
        "entry_price": record.entry_price,
        "stop_loss": record.stop_loss,
        "take_profit": record.take_profit,
        "lot_size": getattr(record, "lot_size", getattr(record, "volume", 0.01)),
        "status": record.status,
        "pnl_usd": getattr(record, "pnl_usd", None),
        "pnl_pct": record.pnl_pct,
        "opened_at": record.opened_at.isoformat() if record.opened_at else None,
        "closed_at": record.closed_at.isoformat() if record.closed_at else None,
        "exit_price": getattr(record, "exit_price", None),
        "exit_reason": getattr(record, "exit_reason", None),
    }


async def handle_get_active_triggers(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"active_triggers": [], "count": 0, "status": "no_session"}

    symbol = args.get("symbol")
    query = (
        select(TradeTrigger, AssetAnalysis)
        .join(AssetAnalysis, TradeTrigger.asset_analysis_id == AssetAnalysis.id)
        .where(TradeTrigger.status == "pending")
    )
    if symbol:
        clean_sym = symbol.strip().upper().replace("/", "")
        query = query.where(AssetAnalysis.symbol == clean_sym)
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
        triggers.append({
            "id": trigger.id,
            "symbol": analysis.symbol,
            "trigger_type": trigger.trigger_type,
            "condition_type": cond.get("condition_type", trigger.trigger_type),
            "trigger_price": cond.get("price") or cond.get("price_level") or cond.get("trigger_price"),
            "direction": cond.get("direction", getattr(analysis, "decision", None)),
            "created_at": trigger.created_at.isoformat() if trigger.created_at else None,
            "condition": cond,
        })
    return {"count": len(triggers), "active_triggers": triggers}


async def handle_get_paper_trading_performance(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"status": "no_session"}
    from utils.analytics.paper_tracker import PaperTracker
    tracker = PaperTracker(settings)
    return await tracker.get_statistics(effective_session)


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


async def handle_get_market_correlations(args: dict, **kwargs) -> dict:
    return {"status": "available", "correlation_matrix": {}}


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
    """Latest per-asset analysis decision for a symbol (Telegram anti-hallucination rule references this tool)."""
    effective_session = session or getattr(executor, "session", None)
    symbol = args.get("symbol") or getattr(executor, "symbol", "")
    if not effective_session:
        return {"error": "Database session required for get_asset_analysis"}
    row = (await effective_session.execute(
        select(AssetAnalysis)
        .where(AssetAnalysis.symbol == symbol)
        .order_by(desc(AssetAnalysis.generated_at))
        .limit(1)
    )).scalars().first()
    if row is None:
        return {"symbol": symbol, "status": "no_analysis", "message": f"No stored analysis found for {symbol}."}
    return {
        "symbol": row.symbol,
        "decision": row.decision,
        "confidence": row.confidence,
        "entry_zone": row.entry_zone,
        "stop_loss": row.stop_loss,
        "take_profit": row.take_profit,
        "rationale": row.rationale,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "debate_verdict": row.debate_verdict,
        "confluence_score": row.confluence_score,
    }
