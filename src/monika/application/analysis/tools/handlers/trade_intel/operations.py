# ==============================================================================
# File: analysis/tools/handlers/trade_intel/operations.py
# ==============================================================================

"""
Price alert, trigger, batch close, risk verdict, and tick flow handlers.
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


async def handle_create_price_alert(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    effective_session = session or getattr(executor, "session", None)
    symbol = (args.get("symbol") or getattr(executor, "symbol", "") or "").strip().upper().replace("/", "")
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
        condition_json=json.dumps(
            {
                "symbol": symbol,
                "price": price_level,
                "target_price": price_level,
                "direction": condition,
                "condition": condition,
                "is_user_alert": True,
                "note": note,
            }
        ),
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
        "message": f"Price alert #{trigger.id} berhasil dibuat untuk {symbol} saat harga {condition} {price_level}",
    }


@register_tool(
    "create_price_alert", aliases=["price_alert", "set_price_alert"], category="EXECUTION", parallel_safe=False
)
class CreatePriceAlertHandler(ToolHandler):
    name = "create_price_alert"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_create_price_alert(args, session=session, executor=executor, **kwargs)


async def handle_get_active_triggers(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
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
        query = query.where(or_(AssetAnalysis.symbol == clean_sym, TradeTrigger.condition_json.like(f"%{clean_sym}%")))
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
        triggers.append(
            {
                "id": trigger.id,
                "symbol": sym,
                "trigger_type": trigger.trigger_type,
                "condition_type": cond.get("condition_type", trigger.trigger_type),
                "trigger_price": cond.get("price")
                or cond.get("price_level")
                or cond.get("trigger_price")
                or cond.get("target_price"),
                "direction": direction,
                "created_at": trigger.created_at.isoformat() if trigger.created_at else None,
                "condition": cond,
            }
        )
    return {"count": len(triggers), "active_triggers": triggers}


@register_tool("get_active_triggers", aliases=["active_triggers"], category="EXECUTION", parallel_safe=True)
class GetActiveTriggersHandler(ToolHandler):
    name = "get_active_triggers"
    category = "EXECUTION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_active_triggers(args, session=session, executor=executor, **kwargs)


async def handle_get_conversation_history(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    effective_session = session or getattr(executor, "session", None)
    limit = int(args.get("limit", 10))
    if not effective_session:
        return {"history": []}
    rows = (
        (
            await effective_session.execute(
                select(TelegramConversation).order_by(desc(TelegramConversation.timestamp)).limit(limit)
            )
        )
        .scalars()
        .all()
    )
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


@register_tool("get_conversation_history", aliases=["conversation_history"], category="SYSTEM", parallel_safe=True)
class GetConversationHistoryHandler(ToolHandler):
    name = "get_conversation_history"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_conversation_history(args, session=session, executor=executor, **kwargs)


async def handle_get_spread_snapshot(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    sym = args.get("symbol") or getattr(executor, "symbol", "EURUSD")
    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        client = get_mt5_client()
        return await client.get_spread(symbol=sym)
    except Exception as e:
        return {"symbol": sym, "status": "error", "error": f"SPREAD_FETCH_FAILED: {e}"}


async def handle_get_market_correlations(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Calculates rolling cross-asset return correlations across market symbols."""
    import monika.core.primitives.clock as clock
    from monika.domain.risk.correlation_matrix import DynamicCorrelationMatrix
    from monika.infrastructure.database.db import get_session

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


@register_tool(
    "get_market_correlations",
    aliases=["market_correlations", "currency_correlation"],
    category="MARKET_DATA",
    parallel_safe=True,
)
class GetMarketCorrelationsHandler(ToolHandler):
    name = "get_market_correlations"
    category = "MARKET_DATA"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_market_correlations(args, session=session, executor=executor, **kwargs)


async def handle_get_recent_activity(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Recent agent activity log entries."""
    from monika.infrastructure.database.models import ActivityLog

    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for get_recent_activity"}
    limit = int(args.get("limit", 10))
    rows = (
        (await effective_session.execute(select(ActivityLog).order_by(desc(ActivityLog.timestamp)).limit(limit)))
        .scalars()
        .all()
    )
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


@register_tool("get_recent_activity", aliases=["recent_activity"], category="SYSTEM", parallel_safe=True)
class GetRecentActivityHandler(ToolHandler):
    name = "get_recent_activity"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_recent_activity(args, session=session, executor=executor, **kwargs)


async def handle_get_asset_analysis(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Latest or historical per-asset analysis decisions for a symbol."""
    effective_session = session or getattr(executor, "session", None)
    symbol = (args.get("symbol") or getattr(executor, "symbol", "") or "").upper().strip().replace("/", "")
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

            dt = datetime.fromisoformat(str(target_date).replace("Z", "+00:00"))
            stmt = stmt.where(AssetAnalysis.generated_at <= dt)
        except Exception:
            pass
    elif hours_back:
        try:
            from datetime import timedelta

            import monika.core.primitives.clock as clock

            cutoff = clock.now() - timedelta(hours=float(hours_back))
            stmt = stmt.where(AssetAnalysis.generated_at >= cutoff)
        except Exception:
            pass

    rows = (
        (await effective_session.execute(stmt.order_by(desc(AssetAnalysis.generated_at)).limit(limit))).scalars().all()
    )

    if not rows:
        return {
            "symbol": symbol or "ALL",
            "status": "no_analysis",
            "message": f"No stored analysis found for {symbol}.",
        }

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


@register_tool("get_asset_analysis", aliases=["asset_analysis"], category="ANALYSIS", parallel_safe=True)
class GetAssetAnalysisHandler(ToolHandler):
    name = "get_asset_analysis"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_asset_analysis(args, session=session, executor=executor, **kwargs)


async def handle_get_latest_risk_verdict(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Retrieve detailed RiskGate rejection reasons and checks passed/failed for latest trade attempt."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for get_latest_risk_verdict"}

    symbol = (args.get("symbol") or getattr(executor, "symbol", "") or "").upper().strip().replace("/", "")

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
            matched.append(
                {
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "category": r.category,
                    "summary": desc_text,
                    "actor": r.actor,
                }
            )
            if len(matched) >= 5:
                break

    return {
        "symbol": symbol or "ALL",
        "recent_risk_events": matched,
        "count": len(matched),
    }


@register_tool(
    "get_latest_risk_verdict",
    aliases=["trade_rejection_reason", "risk_rejection_details"],
    category="RISK",
    parallel_safe=True,
)
class GetLatestRiskVerdictHandler(ToolHandler):
    name = "get_latest_risk_verdict"
    category = "RISK"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_latest_risk_verdict(args, session=session, executor=executor, **kwargs)


async def handle_cancel_stale_pending_orders(args: dict, **kwargs) -> dict:
    """Cancels all resting pending orders older than max_age_hours with confirmation protection."""
    max_age_hours = float(args.get("max_age_hours", 4.0))
    canceled_tickets = []
    failed_tickets = []

    try:
        from monika.core.config.settings import load_settings

        settings = load_settings() or {}
        is_paper = bool(settings.get("trading", {}).get("paper_trading", {}).get("enabled", True))
        if "paper_trading" in settings:
            is_paper = bool(settings.get("paper_trading", {}).get("enabled", is_paper))

        if is_paper:
            # Paper mode: update pending orders in database
            from monika.domain.entities.order_status import OrderStatus
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import Order

            cutoff_ts = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            async with get_session() as s:
                stmt = select(Order).where(
                    Order.status.in_([OrderStatus.PENDING_SUBMIT, OrderStatus.SUBMITTED]),
                    Order.created_at <= cutoff_ts,
                )
                pending_orders = (await s.execute(stmt)).scalars().all()
                for o in pending_orders:
                    o.status = OrderStatus.CANCELLED
                    canceled_tickets.append(o.id)
                await s.commit()

            return {
                "status": "success",
                "mode": "paper",
                "canceled_count": len(canceled_tickets),
                "failed_count": 0,
                "canceled_tickets": canceled_tickets,
                "failed_tickets": [],
                "max_age_hours": max_age_hours,
            }

        # Live broker mode: require explicit confirmation
        confirmed = bool(args.get("confirmed", False))
        if not confirmed:
            return {
                "status": "requires_confirmation",
                "mode": "live",
                "message": "Canceling live pending orders requires explicit human operator confirmation (confirmed=True).",
            }

        from monika.infrastructure.brokers.mt5_client import get_mt5_client

        client = get_mt5_client()
        orders = await client.get_orders()
        now_ts = datetime.now(timezone.utc).timestamp()

        for o in orders:
            ticket = o.get("ticket")
            setup_time = o.get("time_setup", 0)
            age_hours = (now_ts - setup_time) / 3600.0 if setup_time else 0.0

            if age_hours >= max_age_hours and ticket is not None:
                ok = await client.cancel_order(ticket)
                if ok:
                    canceled_tickets.append(ticket)
                else:
                    failed_tickets.append(ticket)

        return {
            "status": "success",
            "mode": "live",
            "canceled_count": len(canceled_tickets),
            "failed_count": len(failed_tickets),
            "canceled_tickets": canceled_tickets,
            "failed_tickets": failed_tickets,
            "max_age_hours": max_age_hours,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed canceling stale orders: {e}"}


@register_tool(
    "cancel_stale_pending_orders",
    aliases=["cancel_old_orders", "purge_stale_orders"],
    category="EXECUTION",
    parallel_safe=False,
)
class CancelStalePendingOrdersHandler(ToolHandler):
    name = "cancel_stale_pending_orders"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_cancel_stale_pending_orders(args, **kwargs)


async def handle_close_positions_batch(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Close batch of positions filtered by profit, loss, or all with confirmation in live mode."""
    filter_type = str(args.get("filter_type") or args.get("filter") or "all").lower().strip()
    reason = str(args.get("reason") or "User requested batch close")

    try:
        from monika.core.config.settings import load_settings

        settings = load_settings() or {}
        is_paper = bool(settings.get("trading", {}).get("paper_trading", {}).get("enabled", True))
        if "paper_trading" in settings:
            is_paper = bool(settings.get("paper_trading", {}).get("enabled", is_paper))

        if is_paper:
            # Paper trading simulation: close open paper positions in database
            from sqlalchemy import select

            from monika.infrastructure.database.models import Position

            closed_count = 0

            async def _close_paper_in_session(s: AsyncSession) -> int:
                count = 0
                stmt = select(Position).where(Position.status == "open")
                positions = (await s.execute(stmt)).scalars().all()
                for p in positions:
                    pnl = p.pnl or 0.0
                    should_close = False
                    if filter_type == "profit" and pnl > 0:
                        should_close = True
                    elif filter_type == "loss" and pnl < 0:
                        should_close = True
                    elif filter_type in ("all", "any"):
                        should_close = True

                    if should_close:
                        p.status = "closed"
                        p.closed_at = datetime.now(timezone.utc)
                        count += 1
                await s.commit()
                return count

            if session:
                closed_count = await _close_paper_in_session(session)
            else:
                from monika.infrastructure.database.db import get_session

                async with get_session() as s:
                    closed_count = await _close_paper_in_session(s)

            return {
                "status": "success",
                "mode": "paper",
                "filter_type": filter_type,
                "closed_count": closed_count,
                "reason": reason,
            }
        else:
            # Live broker mode: require explicit confirmation
            confirmed = bool(args.get("confirmed", False))
            if not confirmed:
                return {
                    "status": "requires_confirmation",
                    "mode": "live",
                    "filter_type": filter_type,
                    "message": "Batch closing live positions requires human operator confirmation (confirmed=True). Propose action first.",
                }

            # Delegate safely through ExecutionService with audit logging
            from monika.application.execution.execution_service import ExecutionService

            exec_svc = ExecutionService(settings=settings)
            res = await exec_svc.close_positions_batch(
                filter_type=filter_type,
                requested_by="tool_call",
                reason=reason,
            )
            return {"status": "success", "mode": "live", "filter_type": filter_type, "result": res}
    except Exception as e:
        return {"status": "error", "filter_type": filter_type, "error": str(e)}


@register_tool(
    "close_positions_batch",
    aliases=["close_profit_positions", "close_loss_positions", "close_filtered_positions"],
    category="EXECUTION",
    parallel_safe=False,
)
class ClosePositionsBatchHandler(ToolHandler):
    name = "close_positions_batch"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_close_positions_batch(args, session=session, executor=executor, **kwargs)


async def handle_get_recent_tick_flow(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Fetch recent tick flow and aggregate tick delta (bid vs ask aggressive volume)."""
    symbol = (args.get("symbol") or "XAUUSD").strip().upper().replace("/", "")
    minutes = int(args.get("minutes", 15))
    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

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


async def handle_export_tick_data(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Exports historical tick flow to CSV file for user analysis."""
    import os
    from pathlib import Path

    symbol = (args.get("symbol") or "XAUUSD").strip().upper().replace("/", "")
    hours = min(int(args.get("hours", 1)), 24)
    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

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


__all__ = [
    "handle_create_price_alert",
    "CreatePriceAlertHandler",
    "handle_get_active_triggers",
    "GetActiveTriggersHandler",
    "handle_get_conversation_history",
    "GetConversationHistoryHandler",
    "handle_get_spread_snapshot",
    "handle_get_market_correlations",
    "GetMarketCorrelationsHandler",
    "handle_get_recent_activity",
    "GetRecentActivityHandler",
    "handle_get_asset_analysis",
    "GetAssetAnalysisHandler",
    "handle_get_latest_risk_verdict",
    "GetLatestRiskVerdictHandler",
    "handle_cancel_stale_pending_orders",
    "CancelStalePendingOrdersHandler",
    "handle_close_positions_batch",
    "ClosePositionsBatchHandler",
    "handle_get_recent_tick_flow",
    "handle_export_tick_data",
]
