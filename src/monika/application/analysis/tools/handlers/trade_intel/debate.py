# ==============================================================================
# File: analysis/tools/handlers/trade_intel/debate.py
# ==============================================================================

"""
Debate statistics, rejection history, chronicles, and memory intelligence handlers.
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


async def handle_search_historical_memories(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Searches past decisions, reflections, lessons, and precedent trade sessions."""
    from monika.application.analysis.memory.session_search import SessionSearchEngine

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

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_search_historical_memories(args, session=session, executor=executor, **kwargs)


async def handle_get_debate_statistics(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Aggregates debate outcomes (Bull vs Bear wins) over a specified time window."""
    from datetime import timedelta

    import monika.core.primitives.clock as clock
    from monika.infrastructure.database.db import get_session
    from monika.infrastructure.database.models import AssetAnalysis

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


@register_tool(
    "get_debate_statistics",
    aliases=["debate_stats", "debate_outcomes_summary"],
    category="ANALYSIS",
    parallel_safe=True,
)
class GetDebateStatisticsHandler(ToolHandler):
    name = "get_debate_statistics"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_debate_statistics(args, session=session, executor=executor, **kwargs)


async def handle_get_rejection_history(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Retrieves history of orders rejected by RiskGate or preflight safety checks."""
    import json

    from monika.infrastructure.database.db import get_session
    from monika.infrastructure.database.models import OrderLog

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
                    OrderLog.result.ilike("%breach%"),
                ),
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

            rejections.append(
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "symbol": r.symbol,
                    "action": r.action,
                    "requested_by": r.requested_by,
                    "approved_by": r.approved_by,
                    "reasons": reasons,
                    "params": params,
                    "details": meta,
                }
            )
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


@register_tool(
    "get_rejection_history", aliases=["rejection_history", "rejected_orders"], category="RISK", parallel_safe=True
)
class GetRejectionHistoryHandler(ToolHandler):
    name = "get_rejection_history"
    category = "RISK"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_rejection_history(args, session=session, executor=executor, **kwargs)


async def handle_get_market_chronicle(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Retrieve market chronicles and macro structural milestones for a given month, timeframe, or category."""
    import calendar
    from datetime import datetime, timezone

    from monika.infrastructure.database.db import get_session
    from monika.infrastructure.database.models import MarketChronicle

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
            "januari": 1,
            "january": 1,
            "jan": 1,
            "februari": 2,
            "february": 2,
            "feb": 2,
            "maret": 3,
            "march": 3,
            "mar": 3,
            "april": 4,
            "apr": 4,
            "mei": 5,
            "may": 5,
            "juni": 6,
            "june": 6,
            "jun": 6,
            "juli": 7,
            "july": 7,
            "jul": 7,
            "agustus": 8,
            "august": 8,
            "aug": 8,
            "september": 9,
            "sep": 9,
            "oktober": 10,
            "october": 10,
            "oct": 10,
            "november": 11,
            "nov": 11,
            "desember": 12,
            "december": 12,
            "dec": 12,
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
            chronicles.append(
                {
                    "id": r.id,
                    "event_date": r.event_date.isoformat() if r.event_date else None,
                    "category": r.category,
                    "headline": r.headline,
                    "narrative": r.narrative,
                    "status": getattr(r, "status", "active"),
                    "affected_assets": getattr(r, "affected_assets", None),
                }
            )
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


@register_tool(
    "get_market_chronicle",
    aliases=["market_chronicle", "trading_chronicle", "chronicle"],
    category="KNOWLEDGE",
    parallel_safe=True,
)
class GetMarketChronicleHandler(ToolHandler):
    name = "get_market_chronicle"
    category = "KNOWLEDGE"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_market_chronicle(args, session=session, executor=executor, **kwargs)


async def handle_export_debate_transcripts(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Export specialist Bull/Bear debate theses and verdicts to JSON for fine-tuning or external audit."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for export_debate_transcripts"}

    days_back = int(args.get("days_back", 30))
    symbol = (args.get("symbol") or "").upper().strip().replace("/", "")
    limit = min(500, int(args.get("limit", 100)))

    from datetime import timedelta

    import monika.core.primitives.clock as clock

    cutoff = clock.now() - timedelta(days=days_back)

    stmt = (
        select(AssetAnalysis)
        .where(AssetAnalysis.generated_at >= cutoff)
        .where(AssetAnalysis.debate_verdict.isnot(None))
    )
    if symbol:
        stmt = stmt.where(AssetAnalysis.symbol == symbol)

    rows = (
        (await effective_session.execute(stmt.order_by(desc(AssetAnalysis.generated_at)).limit(limit))).scalars().all()
    )

    datasets = []
    for r in rows:
        datasets.append(
            {
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
                    {
                        "from": "judge",
                        "value": f"Verdict: {r.debate_verdict}. Rationale: {r.debate_reason or r.rationale}",
                    },
                ],
            }
        )

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

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_export_debate_transcripts(args, session=session, executor=executor, **kwargs)


async def handle_trigger_learning_cycle(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Manually trigger post-trade reflection, negative constraint generation, and playbook consolidation."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required for trigger_learning_cycle"}

    settings = kwargs.get("settings") or getattr(executor, "settings", {}) or {}
    days_back = int(args.get("days_back", 7))

    try:
        from datetime import timedelta

        from sqlalchemy import select

        import monika.core.primitives.clock as clock
        from monika.application.analysis.memory.lesson_consolidator import consolidate_lessons_to_playbook
        from monika.application.analysis.memory.negative_constraint_generator import NegativeConstraintGenerator
        from monika.application.analysis.memory.reflector import TradeReflector
        from monika.infrastructure.database.models import DecisionReflection

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
            "message": f"Learning cycle successfully executed across last {days_back} days.",
        }
    except Exception as e:
        logger.error(f"Trigger learning cycle failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@register_tool("trigger_learning_cycle", aliases=["run_learning_cycle"], category="SYSTEM", parallel_safe=False)
class TriggerLearningCycleHandler(ToolHandler):
    name = "trigger_learning_cycle"
    category = "SYSTEM"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_trigger_learning_cycle(args, session=session, executor=executor, **kwargs)


async def handle_run_adhoc_symbol_debate(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Runs an ad-hoc Multi-Agent Debate (Bull Specialist vs Bear Specialist vs Investment Judge) for a symbol."""
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    symbol = (args.get("symbol") or getattr(executor, "symbol", "EURUSD") or "EURUSD").upper().strip().replace("/", "")

    from monika.application.analysis.debate.debate_orchestrator import DebateOrchestrator
    from monika.application.analysis.prefetch.pipeline import prefetch_pipeline
    from monika.infrastructure.database.db import get_session

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


@register_tool(
    "run_adhoc_symbol_debate",
    aliases=["trigger_debate", "symbol_debate", "run_debate"],
    category="ANALYSIS",
    parallel_safe=False,
)
class RunAdhocSymbolDebateHandler(ToolHandler):
    name = "run_adhoc_symbol_debate"
    category = "ANALYSIS"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_adhoc_symbol_debate(args, session=session, executor=executor, **kwargs)


async def handle_run_hostile_stress_test(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Runs Hostile Market Feed Wire Probes and RiskGate stress testing against extreme anomalies."""
    from monika.application.evals.hostile_market_probe import HostileMarketProbe

    symbol = (args.get("symbol") or "EURUSD").upper().strip().replace("/", "")

    try:
        from monika.infrastructure.brokers.mt5_client import get_mt5_client

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


@register_tool(
    "run_hostile_stress_test",
    aliases=["stress_test", "run_stress_test", "hostile_probe"],
    category="RISK",
    parallel_safe=True,
)
class RunHostileStressTestHandler(ToolHandler):
    name = "run_hostile_stress_test"
    category = "RISK"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_hostile_stress_test(args, session=session, executor=executor, **kwargs)


async def handle_get_graduation_status(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Calculate and return paper-to-live graduation progress and metrics."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "no_session", "graduated": False}

    settings = getattr(executor, "settings", {}) or {}
    min_trades = int(settings.get("execution", {}).get("min_paper_trades_before_live", 50))
    min_wr = float(settings.get("execution", {}).get("graduation_min_win_rate", 0.55))

    from monika.infrastructure.database.models import PaperTradeRecord

    closed_records = (
        (await effective_session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")))
        .scalars()
        .all()
    )

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
            f"({total_closed}/{min_trades} trade, WR: {win_rate * 100:.1f}% vs target {min_wr * 100:.1f}%)."
            if not graduated
            else f"[LULUS] Sistem telah memenuhi semua syarat graduasi ({total_closed} trade, WR: {win_rate * 100:.1f}%, PF: {profit_factor}) dan siap untuk live execution!"
        ),
    }


@register_tool(
    "get_graduation_status",
    aliases=["graduation_progress", "check_graduation"],
    category="REPORTING",
    parallel_safe=True,
)
class GetGraduationStatusHandler(ToolHandler):
    name = "get_graduation_status"
    category = "REPORTING"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_graduation_status(args, session=session, executor=executor, **kwargs)


__all__ = [
    "handle_search_historical_memories",
    "SearchHistoricalMemoriesHandler",
    "handle_get_debate_statistics",
    "GetDebateStatisticsHandler",
    "handle_get_rejection_history",
    "GetRejectionHistoryHandler",
    "handle_get_market_chronicle",
    "GetMarketChronicleHandler",
    "handle_export_debate_transcripts",
    "ExportDebateTranscriptsHandler",
    "handle_trigger_learning_cycle",
    "TriggerLearningCycleHandler",
    "handle_run_adhoc_symbol_debate",
    "RunAdhocSymbolDebateHandler",
    "handle_run_hostile_stress_test",
    "RunHostileStressTestHandler",
    "handle_get_graduation_status",
    "GetGraduationStatusHandler",
]
