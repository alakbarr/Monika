# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/positions.py
# Description: Open positions, batch closure, breakeven, and trailing stop endpoints
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

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Positions")

positions_router = APIRouter()


@positions_router.get("/api/positions", tags=["Positions"])
async def get_positions(
    status: str = Query(default="open", description="Filter by status: open, closed, all"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Daftar historis atau posisi yang masih terbuka dengan data yang diperkaya."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import PositionRepository

    mt5_client = get_dashboard_dependency("mt5_client")

    async with AsyncSessionLocal() as session:
        pos_repo = PositionRepository(session)
        positions = list(await pos_repo.get_recent_positions(limit=limit, status=status))

        current_quotes: Dict[str, dict] = {}
        if mt5_client and status in ("open", "all"):
            unique_symbols = {p.symbol for p in positions if p.symbol and p.status == "open"}
            for sym in unique_symbols:
                try:
                    quote = await mt5_client.get_current_price(sym)
                    if quote:
                        current_quotes[sym] = quote
                except Exception:
                    pass

        results = []
        for p in positions:
            quote = current_quotes.get(p.symbol)
            curr_price = None
            if quote:
                curr_price = quote.get("bid" if (p.direction or "").lower() == "buy" else "ask")

            trailing_data = None
            if p.trailing_override_json:
                try:
                    trailing_data = json.loads(p.trailing_override_json)
                except Exception:
                    trailing_data = p.trailing_override_json

            results.append(
                {
                    "id": p.id,
                    "mt5_ticket": p.mt5_ticket,
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "volume": p.volume,
                    "initial_volume": p.initial_volume,
                    "entry_price": p.entry_price,
                    "price_current": curr_price,
                    "sl": p.sl,
                    "tp": p.tp,
                    "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                    "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                    "status": p.status,
                    "pnl": round(p.pnl, 2) if p.pnl is not None else None,
                    "is_paper": bool(getattr(p, "is_paper", False)),
                    "pair_group_id": p.pair_group_id,
                    "trailing_override": trailing_data,
                    "mae_pips": p.mae_pips,
                    "mfe_pips": p.mfe_pips,
                    "slippage_pips": p.slippage_pips,
                }
            )

        return results


@positions_router.post("/api/actions/close-position", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_close_position(payload: ClosePositionRequest, request: Request):
    """Close floating position in MT5/broker or synthetic paper trade (full or partial)."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import PositionRepository

    exec_svc = get_dashboard_dependency("execution_service")
    mt5_client = get_dashboard_dependency("mt5_client")

    target_ticket = payload.ticket
    target_volume = payload.volume

    async with AsyncSessionLocal() as session:
        pos_repo = PositionRepository(session)
        if target_ticket is None and payload.position_id is not None:
            pos = await pos_repo.get_by_id(payload.position_id)
            if not pos:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": f"Position {payload.position_id} not found."},
                )
            target_ticket = pos.mt5_ticket
            if payload.percentage is not None and target_volume is None and pos.volume:
                target_volume = round(float(pos.volume) * (float(payload.percentage) / 100.0), 2)
            if target_ticket is None and pos.is_paper:
                if exec_svc and hasattr(exec_svc, "_close_paper_position"):
                    res = await exec_svc._close_paper_position(
                        session, pos, requested_by="dashboard", reason=payload.reason, volume=target_volume
                    )
                    return {"status": "success", "result": res}
        elif target_ticket is not None and payload.percentage is not None and target_volume is None:
            pos = await pos_repo.get_by_ticket(target_ticket)
            if pos and pos.volume:
                target_volume = round(float(pos.volume) * (float(payload.percentage) / 100.0), 2)

    if target_ticket is None:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Must provide ticket or position_id."}
        )

    if exec_svc and hasattr(exec_svc, "close_position_by_ticket"):
        close_kwargs: Dict[str, Any] = {
            "ticket": target_ticket,
            "requested_by": "dashboard",
            "reason": payload.reason,
        }
        if target_volume is not None:
            close_kwargs["volume"] = target_volume
        res = await exec_svc.close_position_by_ticket(**close_kwargs)
    elif mt5_client and hasattr(mt5_client, "close_position"):
        close_kwargs = {
            "ticket": target_ticket,
            "comment": f"Close:dashboard"[:31],
        }
        if target_volume is not None:
            close_kwargs["volume"] = target_volume
        res = await mt5_client.close_position(**close_kwargs)
    else:
        from monika.application.services.trading_service import TradingService

        async with AsyncSessionLocal() as session:
            ok = await TradingService.close_position(
                session=session,
                ticket=target_ticket,
                reason=payload.reason or "Closed via dashboard",
                actor="operator:dashboard",
                broker_adapter=mt5_client,
            )
            if ok:
                res = {"success": True, "ticket": target_ticket, "note": "Closed via TradingService"}
            else:
                return JSONResponse(
                    status_code=404, content={"status": "error", "message": f"Ticket {target_ticket} not found."}
                )

    await broadcast_live_event(
        "position_closed",
        {
            "ticket": target_ticket,
            "volume": target_volume,
            "result": res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "status": "success" if res.get("success") else "failed",
        "ticket": target_ticket,
        "volume": target_volume,
        "result": res,
    }


@positions_router.post("/api/positions/{ticket}/breakeven", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_position_breakeven(ticket: int, request: Request):
    """Move Stop Loss to Entry Price (Breakeven) for a single open position."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.application.services.trading_service import TradingService
    from monika.infrastructure.database.repositories import PositionRepository

    exec_svc = get_dashboard_dependency("execution_service")
    mt5_client = get_dashboard_dependency("mt5_client")

    async with AsyncSessionLocal() as session:
        pos_repo = PositionRepository(session)
        pos = await pos_repo.get_by_ticket(ticket, open_only=True)

        if not pos:
            return JSONResponse(
                status_code=404, content={"status": "error", "message": f"Open position #{ticket} not found."}
            )

        entry_price = float(pos.entry_price or 0.0)
        current_sl = float(pos.sl or 0.0) if pos.sl is not None else None
        dir_clean = (pos.direction or "").lower()

        if current_sl is not None:
            if dir_clean == "buy" and current_sl >= entry_price:
                return {"status": "skipped", "message": f"Position #{ticket} SL already at or above breakeven."}
            elif dir_clean == "sell" and current_sl <= entry_price:
                return {"status": "skipped", "message": f"Position #{ticket} SL already at or below breakeven."}

        res = None
        if exec_svc and hasattr(exec_svc, "modify_position_sl_tp"):
            try:
                res = await exec_svc.modify_position_sl_tp(
                    ticket=ticket, new_sl=entry_price, new_tp=pos.tp, comment="BE:dashboard"
                )
            except Exception as e:
                logger.warning(f"Execution service breakeven failed: {e}")

        await TradingService.modify_position(
            session=session,
            ticket=ticket,
            sl=entry_price,
            tp=pos.tp,
            actor="dashboard",
            broker_adapter=mt5_client,
        )

    await broadcast_live_event(
        "position_breakeven",
        {
            "ticket": ticket,
            "entry_price": entry_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "status": "success",
        "ticket": ticket,
        "entry_price": entry_price,
        "result": res or {"success": True, "note": "Updated in DB"},
    }


@positions_router.post("/api/actions/bulk-breakeven", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_bulk_breakeven(payload: BulkBreakevenRequest, request: Request):
    """Move Stop Loss to Entry Price across profitable positions."""
    exec_svc = get_dashboard_dependency("execution_service")
    guardian = get_dashboard_dependency("position_guardian")

    target = exec_svc if (exec_svc and hasattr(exec_svc, "apply_immediate_breakeven")) else guardian

    if target and hasattr(target, "apply_immediate_breakeven"):
        res = await target.apply_immediate_breakeven(
            only_profit=payload.only_profit,
            symbol=payload.symbol,
            requested_by="dashboard_bulk_be",
        )
    else:
        from monika.application.services.trading_service import TradingService
        from monika.infrastructure.database.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            res = await TradingService.bulk_breakeven(
                session=session,
                symbol=payload.symbol,
                actor="dashboard",
            )

    await broadcast_live_event(
        "bulk_breakeven_applied",
        {
            "result": res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"status": "success", "result": res}


@positions_router.post("/api/positions/{ticket}/trailing", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_trailing_override(ticket: int, payload: TrailingOverrideRequest, request: Request):
    """Set dynamic or static trailing stop override per position ticket."""
    from monika.application.services.trading_service import TradingService
    from monika.infrastructure.database.db import AsyncSessionLocal

    if payload.reset_to_default:
        override_data = None
        msg = f"Reset trailing override to default for ticket #{ticket}"
    else:
        override_data = {}
        if payload.enabled is False:
            override_data["disabled"] = True
        if payload.trailing_pips is not None:
            override_data["trailing_pips"] = payload.trailing_pips
        if payload.breakeven_pips is not None:
            override_data["breakeven_pips"] = payload.breakeven_pips
        if payload.trail_atr_multiple is not None:
            override_data["trail_atr_multiple"] = payload.trail_atr_multiple
        msg = f"Updated trailing override for ticket #{ticket}: {override_data}"

    async with AsyncSessionLocal() as session:
        pos = await TradingService.set_trailing_override(
            session=session,
            ticket=ticket,
            override_data=override_data,
            reset_to_default=bool(payload.reset_to_default),
            actor="dashboard",
        )

        if not pos:
            return JSONResponse(
                status_code=404, content={"status": "error", "message": f"Position #{ticket} not found."}
            )

    await broadcast_live_event(
        "trailing_override_updated",
        {
            "ticket": ticket,
            "trailing_override": override_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"status": "success", "ticket": ticket, "message": msg}


@positions_router.post("/api/actions/close-batch", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_close_batch(payload: BatchCloseRequest, request: Request):
    """Close multiple positions selectively in a single batch request."""
    from monika.application.services.trading_service import TradingService
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import PositionRepository

    tickets = list(payload.tickets or [])
    if not tickets:
        async with AsyncSessionLocal() as session:
            pos_repo = PositionRepository(session)
            open_positions = await pos_repo.get_open_positions(
                symbol=payload.symbol.upper() if payload.symbol else None
            )
            for p in open_positions:
                if p.mt5_ticket is not None:
                    tickets.append(p.mt5_ticket)

    exec_svc = get_dashboard_dependency("execution_service")
    emergency = get_dashboard_dependency("emergency_manager") or exec_svc
    mt5_client = get_dashboard_dependency("mt5_client")

    if emergency and hasattr(emergency, "close_positions_batch"):
        res = await emergency.close_positions_batch(
            tickets=tickets,
            requested_by="dashboard_batch_close",
            reason=payload.reason or "Batch close via Dashboard",
        )
    else:
        async with AsyncSessionLocal() as session:
            res = await TradingService.close_positions_batch(
                session=session,
                tickets=tickets,
                reason=payload.reason or "Batch close via Dashboard",
                actor="dashboard",
                broker_adapter=mt5_client,
            )

    await broadcast_live_event(
        "batch_positions_closed",
        {
            "tickets": tickets,
            "result": res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    closed_c = res.get("closed_count", len(tickets)) if isinstance(res, dict) else len(tickets)
    failed_c = res.get("failed_count", 0) if isinstance(res, dict) else 0
    return {
        "status": "success",
        "message": f"Successfully processed batch close: {closed_c} closed",
        "closed_count": closed_c,
        "failed_count": failed_c,
        "result": res,
    }


@positions_router.post("/api/positions/{ticket}/modify", tags=["Actions"])
@require_role(Role.OPERATOR)
async def modify_position(ticket: int, payload: ModifyPositionRequest, request: Request):
    """Modify Stop Loss and Take Profit levels of an active position."""
    from monika.application.services.trading_service import TradingService
    from monika.infrastructure.database.db import AsyncSessionLocal

    exec_svc = get_dashboard_dependency("execution_service")
    mt5_client = get_dashboard_dependency("mt5_client")

    res = None
    if exec_svc and hasattr(exec_svc, "modify_position_sl_tp"):
        try:
            res = await exec_svc.modify_position_sl_tp(
                ticket=ticket,
                new_sl=payload.sl,
                new_tp=payload.tp,
                comment=payload.comment or "Mod:dashboard",
            )
        except Exception as e:
            logger.warning(f"Execution service modify failed: {e}")

    async with AsyncSessionLocal() as session:
        ok = await TradingService.modify_position(
            session=session,
            ticket=ticket,
            sl=payload.sl,
            tp=payload.tp,
            actor="dashboard",
            broker_adapter=mt5_client,
        )
        if ok and not res:
            res = {"success": True, "ticket": ticket, "note": "Updated via TradingService"}

    if not res:
        return JSONResponse(
            status_code=404, content={"status": "error", "message": f"Position with ticket {ticket} not found."}
        )

    await broadcast_live_event(
        "position_modified",
        {
            "ticket": ticket,
            "sl": payload.sl,
            "tp": payload.tp,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"status": "success", "result": res}
