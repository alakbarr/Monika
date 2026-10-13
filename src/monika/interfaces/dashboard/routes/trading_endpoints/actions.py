# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/actions.py
# Description: Operator commands, kill switches, cycle triggers, and trade approvals
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from monika.interfaces.dashboard.rbac import Role, require_role
from monika.interfaces.dashboard.routes.common import (
    BatchCloseRequest,
    BulkBreakevenRequest,
    ClosePositionRequest,
    ManualOrderPreviewRequest,
    ManualOrderSubmitRequest,
    ModifyPositionRequest,
    OverrideRiskRequest,
    SteerRequest,
    TrailingOverrideRequest,
    TriggerCycleRequest,
    _safe_json,
    broadcast_live_event,
    get_dashboard_dependency,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Actions")

actions_router = APIRouter()


@actions_router.post("/api/actions/trigger-cycle", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_trigger_cycle(request: Request, body: Optional[TriggerCycleRequest] = None):
    """Trigger the LangGraph analysis cycle immediately with optional symbol and context guidance."""
    body = body or TriggerCycleRequest()
    cycle_sched = get_dashboard_dependency("cycle_scheduler")
    if not cycle_sched:
        return JSONResponse(
            status_code=503, content={"status": "error", "message": "CycleScheduler is not initialized or registered."}
        )

    if hasattr(cycle_sched, "_cycle_lock") and cycle_sched._cycle_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"status": "skipped", "message": "An analysis cycle is already actively executing."},
        )

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import ActivityLog, UserMarketIntel, _utcnow

    if body.symbol or body.context:
        try:
            async with AsyncSessionLocal() as session:
                intel = UserMarketIntel(
                    telegram_user_id="operator_dashboard",
                    intel_type="tactical_directive",
                    title="Manual Cycle Directive",
                    summary=f"Focus cycle on {body.symbol or 'ALL'}. Context: {body.context or body.reason}",
                    directive="neutral",
                    target_cycle="next_cycle_only",
                    affected_symbols=body.symbol or "ALL",
                    is_active=True,
                    created_at=_utcnow(),
                )
                session.add(intel)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to record tactical directive for trigger-cycle: {e}")

    asyncio.create_task(cycle_sched.run_once(forced=body.forced))

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                ActivityLog(
                    category="system",
                    description=f"Analysis cycle manually triggered via Dashboard ({body.reason}, symbol={body.symbol})",
                    actor="dashboard",
                )
            )
            await session.commit()
    except Exception as e:
        logger.debug(f"Failed to log dashboard activity: {e}")

    await broadcast_live_event(
        "cycle_triggered",
        {
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "forced": body.forced,
            "reason": body.reason,
            "symbol": body.symbol,
        },
    )

    return {
        "status": "triggered",
        "message": "Analysis cycle dispatched successfully.",
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "forced": body.forced,
        "symbol": body.symbol,
    }


@actions_router.post("/api/actions/steer", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_steer(body: SteerRequest, request: Request):
    """Inject operator steering instruction / directive into active or next cycle."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import ActivityLog, UserMarketIntel, _utcnow

    now = _utcnow()
    symbols_str = ",".join(body.symbols) if body.symbols else "ALL"

    try:
        async with AsyncSessionLocal() as session:
            intel = UserMarketIntel(
                telegram_user_id="operator_dashboard",
                intel_type="tactical_directive",
                title="Operator Steer Directive",
                summary=body.message,
                directive="neutral",
                target_cycle="next_cycle_only" if body.mode == "follow_up" else "continuous",
                affected_symbols=symbols_str,
                is_active=True,
                created_at=now,
            )
            session.add(intel)
            session.add(
                ActivityLog(
                    category="analysis",
                    description=f"Operator steer injected ({body.mode}): {body.message[:150]}",
                    actor="operator",
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to persist operator steer directive: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    await broadcast_live_event(
        "steer_injected",
        {
            "message": body.message,
            "mode": body.mode,
            "symbols": body.symbols,
            "injected_at": now.isoformat(),
        },
    )

    return {
        "status": "steered",
        "message": "Steer directive successfully recorded and broadcasted.",
        "mode": body.mode,
        "injected_at": now.isoformat(),
    }


@actions_router.post("/api/actions/kill-symbol/{symbol}", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_kill_symbol(symbol: str, request: Request):
    """Emergency close all open positions for a single currency/symbol."""
    sym = symbol.strip().upper().replace("/", "")
    exec_svc = get_dashboard_dependency("execution_service")
    emergency = get_dashboard_dependency("emergency_manager") or exec_svc

    if emergency and hasattr(emergency, "close_positions_batch"):
        res = await emergency.close_positions_batch(
            symbol=sym,
            requested_by="dashboard_kill_symbol",
            reason=f"Emergency liquidation for symbol {sym}",
        )
    else:
        from sqlalchemy import select

        from monika.infrastructure.database.db import AsyncSessionLocal
        from monika.infrastructure.database.models import ActivityLog, Position

        async with AsyncSessionLocal() as session:
            positions = (
                (await session.execute(select(Position).where(Position.symbol == sym, Position.status == "open")))
                .scalars()
                .all()
            )
            for p in positions:
                p.status = "closed"
                p.closed_at = datetime.now(timezone.utc)
            session.add(
                ActivityLog(
                    category="risk",
                    description=f"Symbol {sym} liquidated ({len(positions)} positions closed)",
                    actor="admin",
                )
            )
            await session.commit()
            res = {"success": True, "closed_count": len(positions), "symbol": sym}

    await broadcast_live_event(
        "symbol_liquidated",
        {
            "symbol": sym,
            "result": res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"status": "success", "symbol": sym, "result": res}


@actions_router.post("/api/actions/emergency-kill", tags=["Actions"])
@actions_router.post("/api/kill", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_emergency_kill(request: Request):
    """Trigger emergency kill switch and position liquidation safely via daemon."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import ActivityLogRepository, SystemConfigRepository

    async with AsyncSessionLocal() as session:
        cfg_repo = SystemConfigRepository(session)
        act_repo = ActivityLogRepository(session)
        await cfg_repo.set_kill_switch(True)
        await act_repo.log_activity(
            category="system",
            description="Emergency kill switch activated via Dashboard / CLI",
            actor="admin",
        )
        await session.commit()

    exec_svc = get_dashboard_dependency("execution_service")
    guardian = get_dashboard_dependency("position_guardian")
    if exec_svc and hasattr(exec_svc, "kill_switch"):
        await exec_svc.kill_switch("Dashboard emergency kill switch")
    elif guardian and hasattr(guardian, "execution_service") and hasattr(guardian.execution_service, "kill_switch"):
        await guardian.execution_service.kill_switch("Dashboard emergency kill switch")

    await broadcast_live_event(
        "kill_switch_activated",
        {
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Emergency kill switch triggered",
        },
    )
    return {"status": "success", "message": "Emergency kill switch activated. Position closures completed."}


@actions_router.post("/api/actions/resume", tags=["Actions"])
@actions_router.post("/api/actions/resume-trading", tags=["Actions"])
@actions_router.post("/api/resume", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_resume_trading(request: Request):
    """Resume system trading operations, clearing kill switch, pause flags, and resetting EffectGate."""
    from monika.infrastructure.database.db import AsyncSessionLocal

    exec_svc = get_dashboard_dependency("execution_service")
    risk_gate = get_dashboard_dependency("risk_gate")

    async with AsyncSessionLocal() as session:
        if exec_svc and hasattr(exec_svc, "resume_trading"):
            res = await exec_svc.resume_trading(session, requested_by="dashboard_admin")
        elif risk_gate and hasattr(risk_gate, "resume_trading"):
            await risk_gate.resume_trading(session)
            res = {"success": True, "message": "Trading resumed via RiskGate."}
        else:
            from monika.domain.risk.risk_gate import RiskGate

            settings = get_dashboard_dependency("settings") or {}
            gate = RiskGate(settings)
            await gate.resume_trading(session)
            res = {"success": True, "message": "Trading resumed."}

    await broadcast_live_event(
        "trading_resumed",
        {
            "resumed_at": datetime.now(timezone.utc).isoformat(),
            "actor": "admin",
        },
    )
    return {"status": "success", "message": "Trading resumed. All pause & kill flags cleared, EffectGate reset."}


@actions_router.post("/api/actions/pause", tags=["Actions"])
@actions_router.post("/api/actions/pause-trading", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_pause_trading(request: Request):
    """Pause system trading operations."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import SystemConfigRepository

    async with AsyncSessionLocal() as session:
        cfg_repo = SystemConfigRepository(session)
        await cfg_repo.set_system_paused(True)
        await session.commit()

    await broadcast_live_event(
        "system_state_change",
        {
            "state": "paused",
            "reason": "Dashboard/CLI pause command",
            "paused_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"status": "success", "message": "System trading paused."}


@actions_router.post("/api/actions/unsuspend", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_unsuspend_symbols(request: Request):
    """Lift trading suspension on all instruments or specific symbol."""
    from monika.core.analytics.paper_tracker import PaperTracker
    from monika.infrastructure.database.db import AsyncSessionLocal

    try:
        body = await request.json()
    except Exception:
        body = {}

    symbol = body.get("symbol")
    async with AsyncSessionLocal() as session:
        tracker = PaperTracker()
        if not symbol or str(symbol).upper() == "ALL":
            cleared = await tracker.unsuspend_all(session)
            sym_list = cleared
        else:
            sym_upper = str(symbol).strip().upper()
            ok = await tracker.unsuspend_symbol(session, sym_upper)
            sym_list = [sym_upper] if ok else []

    await broadcast_live_event(
        "symbols_unsuspended",
        {
            "symbols": sym_list,
            "cleared_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"status": "success", "cleared": sym_list}


@actions_router.api_route("/api/actions/approve-trade/{trade_id}", methods=["POST", "PUT"], tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_approve_trade(trade_id: int, request: Request):
    """Approve a pending trade trigger or asset analysis for order execution."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import ActivityLog, AssetAnalysis, TradeTrigger

    exec_svc = get_dashboard_dependency("execution_service")

    async with AsyncSessionLocal() as session:
        trigger = (await session.execute(select(TradeTrigger).where(TradeTrigger.id == trade_id))).scalar_one_or_none()

        if trigger:
            trigger.status = "approved"
            trigger.fired_at = datetime.now(timezone.utc)
            session.add(
                ActivityLog(
                    category="trading",
                    description=f"TradeTrigger #{trade_id} approved via Dashboard",
                    actor="dashboard",
                    related_id=trade_id,
                )
            )
            await session.commit()

            await broadcast_live_event(
                "trade_approved",
                {
                    "trade_id": trade_id,
                    "type": "TradeTrigger",
                    "status": "approved",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            return {
                "status": "success",
                "type": "TradeTrigger",
                "id": trade_id,
                "message": f"TradeTrigger #{trade_id} approved.",
            }

        analysis = (
            await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == trade_id))
        ).scalar_one_or_none()

    if not analysis:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"No pending trade or trigger found with ID {trade_id}."},
        )

    if analysis.decision not in ("buy", "sell"):
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": f"AssetAnalysis #{trade_id} has non-tradeable decision '{analysis.decision}'.",
            },
        )

    async with AsyncSessionLocal() as session:
        analysis_db = (
            await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == trade_id))
        ).scalar_one_or_none()

        if exec_svc and analysis_db:
            exec_result = await exec_svc.execute_analysis(session, analysis_db)
            await session.commit()
            res_dict = {
                "executed": exec_result.executed,
                "ticket": exec_result.mt5_ticket,
                "price": exec_result.executed_price,
                "lots": exec_result.executed_lots,
                "error": exec_result.mt5_error,
            }
        elif analysis_db:
            analysis_db.execution_status = "approved_manual"
            await session.commit()
            res_dict = {"executed": False, "note": "Marked approved_manual (standalone mode)"}
        else:
            return JSONResponse(
                status_code=404, content={"status": "error", "message": f"AssetAnalysis #{trade_id} missing."}
            )

    await broadcast_live_event(
        "trade_approved",
        {
            "trade_id": trade_id,
            "type": "AssetAnalysis",
            "result": res_dict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "status": "success",
        "type": "AssetAnalysis",
        "id": trade_id,
        "execution": res_dict,
    }
