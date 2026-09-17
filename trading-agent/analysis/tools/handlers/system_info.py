# ==============================================================================
# File: analysis/tools/handlers/system_info.py
# ==============================================================================

"""
System status, observability, and calibration tool handlers.
Direct execution without circular trampolines.
"""

from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import RiskState, FundamentalBrief, ActivityLog, SystemConfig
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


def _get_session_and_settings(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    return session, settings


async def handle_get_system_health(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"status": "HEALTHY", "trading_paused": False, "mode": "paper"}

    today_start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    risk = (await effective_session.execute(
        select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
    )).scalar_one_or_none()

    last_brief = (await effective_session.execute(
        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
    )).scalar_one_or_none()

    cutoff_err = clock.now() - timedelta(hours=2)
    recent_errors = (await effective_session.execute(
        select(ActivityLog)
        .where(ActivityLog.timestamp >= cutoff_err)
        .where(ActivityLog.category.in_(["error", "system_error", "exception"]))
        .order_by(ActivityLog.timestamp.desc())
        .limit(5)
    )).scalars().all()

    mt5_cfg = (await effective_session.execute(
        select(SystemConfig).where(SystemConfig.key == "mt5_real_risk_state")
    )).scalar_one_or_none()

    mt5_connected = False
    if mt5_cfg and mt5_cfg.value:
        try:
            import json as _j
            val = _j.loads(mt5_cfg.value)
            upd = datetime.fromisoformat(val.get("updated_at", "2000-01-01"))
            if upd.tzinfo is None:
                upd = upd.replace(tzinfo=timezone.utc)
            mt5_connected = (clock.now() - upd).total_seconds() < 180
        except Exception:
            pass

    return {
        "status": "PAUSED" if (risk and risk.trading_paused) else "HEALTHY",
        "trading_paused": risk.trading_paused if risk else False,
        "pause_reason": risk.reason if (risk and risk.trading_paused) else None,
        "daily_pnl_pct": risk.daily_pnl if risk else 0.0,
        "current_drawdown": risk.current_drawdown if risk else 0.0,
        "last_analysis_cycle": last_brief.generated_at.isoformat() if last_brief else "No cycle recorded",
        "mt5_bridge_connected": mt5_connected,
        "recent_errors_2h_count": len(recent_errors),
        "recent_errors_sample": [e.description for e in recent_errors[:3]],
        "mode": "paper" if settings.get("paper_trading", {}).get("enabled", True) else "live",
    }


async def handle_get_edge_tracker_status(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"edge_status": "insufficient_data", "win_rate_pct": 0}

    days_back = int(args.get("days_back", 30))
    try:
        from utils.analytics.edge_tracker import compute_edge_status
        from utils.analytics.analysis_tracker import compute_factor_effectiveness
        edge = await compute_edge_status(effective_session)
        factors = await compute_factor_effectiveness(effective_session, days_back)
        top_factors = sorted(factors.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True)
        factor_summary = [
            {"factor": f, "win_rate": d.get("win_rate", 0), "wins": d.get("wins", 0), "total": d.get("total", 0)}
            for f, d in top_factors if d.get("total", 0) > 0
        ]
        return {
            "edge_status": edge.get("status"),
            "win_rate_pct": edge.get("win_rate", 0),
            "ci_lower_pct": edge.get("ci_lower", 0),
            "ci_upper_pct": edge.get("ci_upper", 0),
            "z_score": edge.get("z_score", 0),
            "is_statistically_significant": (edge.get("z_score", 0) or 0) > 1.645,
            "action_recommendation": edge.get("action", ""),
            "top_confluence_factors": factor_summary[:7],
        }
    except Exception as e:
        return {"edge_status": "error", "error": str(e)}


async def handle_get_calibration_status(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"status": "no_session"}

    try:
        import json as _j
        from utils.analytics.specialist_tracker import compute_specialist_reliability
        from utils.protocol.enhanced_cds import get_cds_thresholds_async
        from utils.analytics.agent_performance_monitor import get_currency_confidence_ceiling

        cal_cfg = (await effective_session.execute(
            select(SystemConfig).where(SystemConfig.key == "system_calibration_directives")
        )).scalar_one_or_none()
        directives = _j.loads(cal_cfg.value) if (cal_cfg and cal_cfg.value) else {}

        ceilings = await get_currency_confidence_ceiling(effective_session, days_back=30)
        cds_thresholds = await get_cds_thresholds_async(effective_session, settings)
        specialists = await compute_specialist_reliability(effective_session)

        return {
            "news_directives": directives,
            "currency_confidence_ceilings": ceilings,
            "cds_thresholds": cds_thresholds,
            "specialist_trust_weights": specialists.get("specialists", {}),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def handle_get_token_usage_and_costs(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"total_cost_usd": 0.0, "total_tokens": 0}

    try:
        from database.models import TokenUsageLog
        days_back = int(args.get("days_back", 1))
        cutoff = clock.now() - timedelta(days=days_back)

        rows = (await effective_session.execute(
            select(
                TokenUsageLog.model_name,
                func.sum(TokenUsageLog.input_tokens).label("in_tokens"),
                func.sum(TokenUsageLog.output_tokens).label("out_tokens"),
                func.count(TokenUsageLog.id).label("calls_count"),
            )
            .where(TokenUsageLog.timestamp >= cutoff)
            .group_by(TokenUsageLog.model_name)
        )).all()

        breakdown = []
        total_cost = 0.0
        total_tokens = 0
        for r in rows:
            in_t = int(r.in_tokens or 0)
            out_t = int(r.out_tokens or 0)
            tot_t = in_t + out_t
            total_tokens += tot_t
            breakdown.append({
                "model": r.model_name,
                "input_tokens": in_t,
                "output_tokens": out_t,
                "calls": int(r.calls_count or 0),
            })

        return {
            "days_back": days_back,
            "total_tokens": total_tokens,
            "models_breakdown": breakdown,
        }
    except Exception as e:
        return {"total_tokens": 0, "error": str(e)}


async def handle_get_market_session(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    from analysis.tools.domain.macro_handlers import MacroToolHandlers
    settings = getattr(executor, "settings", {}) or {}
    handlers = getattr(executor, "macro_handlers", None) or MacroToolHandlers(settings)
    return await handlers.get_market_session(session=session, **args)


async def handle_get_market_regime(args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    symbol = sym or args.get("symbol") or getattr(executor, "symbol", "EURUSD")
    timeframe = args.get("timeframe", "H4")
    settings = getattr(executor, "settings", {}) or {}
    try:
        from analysis.calculators.regime_classifier import compute_bollinger_donchian_chop
        return await compute_bollinger_donchian_chop(effective_session, symbol, timeframe, settings)
    except Exception as e:
        return {"symbol": symbol, "timeframe": timeframe, "regime": "TRENDING", "note": str(e)}


@register_tool("get_system_health", aliases=["system_health"], category="SYSTEM", parallel_safe=True)
class GetSystemHealthHandler(ToolHandler):
    name = "get_system_health"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_system_health(args, session=session, executor=executor, **kwargs)


@register_tool("get_edge_tracker_status", aliases=["edge_tracker"], category="SYSTEM", parallel_safe=True)
class GetEdgeTrackerStatusHandler(ToolHandler):
    name = "get_edge_tracker_status"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_edge_tracker_status(args, session=session, executor=executor, **kwargs)


@register_tool("get_calibration_status", aliases=["calibration_status"], category="SYSTEM", parallel_safe=True)
class GetCalibrationStatusHandler(ToolHandler):
    name = "get_calibration_status"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_calibration_status(args, session=session, executor=executor, **kwargs)


@register_tool("get_token_usage_and_costs", aliases=["token_usage"], category="SYSTEM", parallel_safe=True)
class GetTokenUsageAndCostsHandler(ToolHandler):
    name = "get_token_usage_and_costs"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_token_usage_and_costs(args, session=session, executor=executor, **kwargs)


@register_tool("get_market_session", aliases=["get_market_sessions", "market_session"], category="MACRO", parallel_safe=True)
class GetMarketSessionHandler(ToolHandler):
    name = "get_market_session"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_market_session(args, session=session, executor=executor, **kwargs)


@register_tool("get_market_regime", aliases=["market_regime"], category="TECHNICAL", parallel_safe=True)
class GetMarketRegimeHandler(ToolHandler):
    name = "get_market_regime"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_market_regime(args, session=session, executor=executor, **kwargs)
