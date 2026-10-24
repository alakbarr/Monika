# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/orders.py
# Description: Order ledger, preview, and manual order execution endpoints
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

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Orders")

orders_router = APIRouter()


@orders_router.get("/api/v1/orders", tags=["Orders"])
async def get_orders(
    limit: int = Query(default=30, ge=1, le=100),
    action: Optional[str] = Query(default=None, description="Filter: place, modify, close"),
):
    """Audit trail percobaan order (sukses & gagal/tolak)."""
    from monika.application.services.portfolio_service import PortfolioService
    from monika.infrastructure.database.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        orders = await PortfolioService.get_order_logs(session=session, limit=limit, action=action)

        return [
            {
                "id": o.id,
                "action": o.action,
                "symbol": o.symbol,
                "params": _safe_json(o.params_json),
                "requested_by": o.requested_by,
                "approved_by": o.approved_by,
                "result": _safe_json(o.result),
                "timestamp": o.timestamp.isoformat() if o.timestamp else None,
            }
            for o in orders
        ]


@orders_router.post("/api/v1/orders/preview", tags=["Trading"])
@require_role(Role.OPERATOR)
async def preview_manual_order(payload: ManualOrderPreviewRequest, request: Request):
    """Preview manual order metrics: lot sizing, risk amount, reward amount, RR ratio, margin."""
    sym = payload.symbol.strip().upper().replace("/", "")
    direction = payload.direction.strip().lower()

    mt5_client = get_dashboard_dependency("mt5_client")
    risk_gate = get_dashboard_dependency("risk_gate")

    entry_price = payload.price or payload.entry_price
    if mt5_client:
        try:
            quote = await mt5_client.get_current_price(sym)
            if quote:
                bid = quote.get("bid")
                ask = quote.get("ask")
                if entry_price is None:
                    entry_price = ask if direction == "buy" else bid
        except Exception:
            pass

    if entry_price is None or entry_price <= 0:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "message": f"Market price quote unavailable for {sym}. Cannot evaluate trade proposal (Fail-Closed).",
            },
        )

    is_jpy = "JPY" in sym
    pip_factor = 0.01 if is_jpy else 0.0001

    sl_distance_pips = abs(entry_price - payload.sl) / pip_factor if payload.sl else None
    tp_distance_pips = abs(payload.tp - entry_price) / pip_factor if payload.tp else None

    volume = payload.volume or payload.fixed_lots or 0.1
    pip_value_approx = 10.0 * volume

    estimated_risk_usd = round(sl_distance_pips * pip_value_approx, 2) if sl_distance_pips else None
    estimated_reward_usd = round(tp_distance_pips * pip_value_approx, 2) if tp_distance_pips else None
    rr_ratio = (
        round(tp_distance_pips / sl_distance_pips, 2)
        if (sl_distance_pips and tp_distance_pips and sl_distance_pips > 0)
        else None
    )

    from monika.infrastructure.database.db import AsyncSessionLocal

    is_allowed = False
    gate_reason = "Order within risk thresholds"
    if risk_gate:
        try:
            async with AsyncSessionLocal() as session:
                allowed, reason = await risk_gate._check_not_paused(session)
                if allowed:
                    is_allowed = True
                else:
                    is_allowed = False
                    gate_reason = reason
        except Exception as e:
            is_allowed = False
            gate_reason = f"Risk evaluation failed closed: {e}"
    else:
        is_allowed = False
        gate_reason = "RiskGate unavailable; orders rejected by default"

    return {
        "symbol": sym,
        "direction": direction,
        "entry_price": entry_price,
        "sl": payload.sl,
        "tp": payload.tp,
        "volume": volume,
        "sl_distance_pips": round(sl_distance_pips, 1) if sl_distance_pips else None,
        "tp_distance_pips": round(tp_distance_pips, 1) if tp_distance_pips else None,
        "estimated_risk_usd": estimated_risk_usd,
        "estimated_reward_usd": estimated_reward_usd,
        "rr_ratio": rr_ratio,
        "risk_gate_allowed": is_allowed,
        "risk_gate_reason": gate_reason,
    }


@orders_router.post("/api/v1/orders/submit", tags=["Trading"])
@require_role(Role.OPERATOR)
async def submit_manual_order(payload: ManualOrderSubmitRequest, request: Request):
    """Execute a manual trade order directly to MT5 or broker."""
    sym = payload.symbol.strip().upper().replace("/", "")
    direction = payload.direction.strip().lower()
    volume = payload.volume or payload.lots or 0.1

    mt5_client = get_dashboard_dependency("mt5_client")
    exec_svc = get_dashboard_dependency("execution_service")
    settings = get_dashboard_dependency("settings")
    if not settings:
        try:
            from monika.core.config.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}

    from monika.domain.risk.trade_proposal import TradeProposal
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import ActivityLogRepository

    risk_gate = get_dashboard_dependency("risk_gate")
    if not risk_gate:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "RiskGate tidak tersedia. Pengiriman order diblokir oleh Mechanical Fortress Principle.",
            },
        )

    pt_setting = (
        settings.get("trading", {}).get("paper_trading", {}) if isinstance(settings.get("trading"), dict) else {}
    )
    if isinstance(pt_setting, dict):
        is_paper_setting = bool(pt_setting.get("enabled", True))
    elif isinstance(pt_setting, bool):
        is_paper_setting = pt_setting
    else:
        is_paper_setting = True
    is_paper = payload.is_paper if payload.is_paper is not None else is_paper_setting
    if not is_paper:
        user_role = getattr(request.state, "role", None)
        if user_role != Role.ADMIN:
            return JSONResponse(
                status_code=403,
                content={
                    "status": "forbidden",
                    "message": "Live real-capital manual order submission requires Role.ADMIN privilege.",
                },
            )

    dir_upper = direction.upper()
    prop_dir: Literal["BUY", "SELL", "WAIT"] = (
        "BUY" if dir_upper == "BUY" else ("SELL" if dir_upper == "SELL" else "WAIT")
    )

    proposal = TradeProposal(
        symbol=sym,
        direction=prop_dir,
        entry_price=payload.price or 0.0,
        stop_loss=payload.sl or 0.0,
        take_profit=payload.tp or 0.0,
        lot_size=volume,
        confluence_score=75.0,
        metadata={"source": "manual:dashboard"},
    )

    async with AsyncSessionLocal() as session:
        verdict = await risk_gate.evaluate_proposal(session, proposal, is_paper=is_paper)
        if not verdict.approved:
            act_repo = ActivityLogRepository(session)
            await act_repo.log_activity(
                category="risk",
                description=f"Manual order rejected by RiskGate: {direction.upper()} {volume} {sym} - {', '.join(verdict.rejection_reasons)}",
                actor="operator",
            )
            await session.commit()
            return JSONResponse(
                status_code=400,
                content={
                    "status": "rejected",
                    "message": f"Order ditolak oleh RiskGate: {', '.join(verdict.rejection_reasons)}",
                    "rejection_reasons": verdict.rejection_reasons,
                },
            )

    entry_price = payload.price
    if not entry_price and mt5_client and hasattr(mt5_client, "get_current_price"):
        try:
            tick = await mt5_client.get_current_price(sym)
            if tick:
                entry_price = tick.get("ask") if direction == "buy" else tick.get("bid")
        except Exception:
            pass
    if not entry_price or entry_price <= 0:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "message": f"Valid market entry price unavailable for symbol {sym}. Order submission rejected.",
            },
        )

    from monika.application.services.trading_service import TradingService

    async with AsyncSessionLocal() as session:
        exec_res = await TradingService.submit_order(
            session=session,
            symbol=sym,
            action=direction,
            volume=volume,
            entry_price=entry_price,
            stop_loss=payload.sl,
            take_profit=payload.tp,
            is_paper=is_paper,
            actor="operator:dashboard",
            broker_adapter=mt5_client,
            risk_gate=risk_gate,
        )

    if not exec_res.success:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": exec_res.error_message or "Order execution failed"},
        )

    res = {
        "success": True,
        "ticket": exec_res.ticket,
        "price": exec_res.price,
        "is_paper": exec_res.is_paper,
        "message": "Order executed successfully via TradingService",
    }

    await broadcast_live_event(
        "manual_order_submitted",
        {
            "symbol": sym,
            "direction": direction,
            "volume": volume,
            "is_paper": is_paper,
            "result": res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "status": "success" if (res and res.get("success")) else "failed",
        "is_paper": is_paper,
        "result": res,
    }
