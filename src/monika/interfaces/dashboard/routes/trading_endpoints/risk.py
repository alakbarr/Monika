# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/risk.py
# Description: Risk dashboard, scorecards, correlation matrices, and override controls
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

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Risk")

risk_router = APIRouter()


@risk_router.get("/api/risk", tags=["Risk"])
async def get_risk():
    """State PnL hari ini, status auto-trading (paused/active), margin, dan parameter risiko."""
    from sqlalchemy import desc, select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import PaperTradeRecord, Position, RiskState

    settings = get_dashboard_dependency("settings") or {}
    trading_risk = settings.get("trading", {}).get("risk", {}) if isinstance(settings, dict) else {}
    max_risk_pct = float(trading_risk.get("risk_percent_per_trade", 1.0))
    max_daily_dd = float(trading_risk.get("max_daily_drawdown_percent", 3.0))
    max_positions = int(trading_risk.get("max_concurrent_positions", 5))

    now_utc = datetime.now(timezone.utc)
    is_weekend = now_utc.weekday() >= 5

    mt5_client = get_dashboard_dependency("mt5_client")
    account_info = None
    if mt5_client and hasattr(mt5_client, "get_account_info"):
        try:
            account_info = await mt5_client.get_account_info()
        except Exception:
            pass

    async with AsyncSessionLocal() as session:
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        risk = (
            await session.execute(
                select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
            )
        ).scalar_one_or_none()

        # Count real consecutive losses from closed trades
        consecutive_losses = 0
        recent_closed = (
            await session.execute(
                select(PaperTradeRecord.exit_reason, PaperTradeRecord.pnl_pct)
                .where(PaperTradeRecord.status == "closed")
                .order_by(PaperTradeRecord.closed_at.desc())
                .limit(10)
            )
        ).all()
        for row in recent_closed:
            pnl = row.pnl_pct or 0.0
            if row.exit_reason == "sl_hit" or pnl < 0:
                consecutive_losses += 1
            else:
                break

        # Open positions count for exposure estimation
        open_pos_count = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
        active_pos_count = len(open_pos_count)

        # Margin and exposure calculations
        margin_used = 0.0
        margin_free = 0.0
        margin_level_pct = 0.0
        margin_usage_pct = 0.0

        if account_info and isinstance(account_info, dict):
            equity = float(account_info.get("equity") or 0.0)
            margin_used = float(account_info.get("margin") or 0.0)
            margin_free = float(account_info.get("margin_free") or 0.0)
            margin_level_pct = float(account_info.get("margin_level") or 0.0)
            margin_usage_pct = (margin_used / equity * 100.0) if equity > 0 else 0.0
        else:
            # Synthetic approximation if broker offline
            margin_usage_pct = round(active_pos_count * 2.5, 2)

        total_open_risk_pct = round(active_pos_count * max_risk_pct, 2)

        if not risk:
            return {
                "date": now_utc.date().isoformat(),
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
                "current_drawdown": 0.0,
                "trading_paused": False,
                "reason": None,
                "margin_used": round(margin_used, 2),
                "margin_free": round(margin_free, 2),
                "margin_level_pct": round(margin_level_pct, 2),
                "margin_usage_pct": round(margin_usage_pct, 2),
                "total_open_risk_pct": total_open_risk_pct,
                "consecutive_losses": consecutive_losses,
                "max_consecutive_losses": 3,
                "max_risk_pct": max_risk_pct,
                "max_daily_drawdown_pct": max_daily_dd,
                "max_positions": max_positions,
                "avg_spread_pips": 1.2,
                "avg_rr_ratio": 1.5,
                "is_weekend": is_weekend,
            }

        daily_pnl_pct = getattr(risk, "daily_pnl_pct", None)
        starting_bal = getattr(risk, "starting_balance", None)
        if daily_pnl_pct is None and hasattr(risk, "daily_pnl") and starting_bal:
            daily_pnl_pct = (risk.daily_pnl / starting_bal) * 100
        elif daily_pnl_pct is None:
            daily_pnl_pct = 0.0

        return {
            "date": (
                risk.date.date() if hasattr(risk.date, "date") and callable(getattr(risk.date, "date")) else risk.date
            ).isoformat()
            if risk.date
            else None,
            "daily_pnl": round(risk.daily_pnl, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "current_drawdown": round(risk.current_drawdown, 2),
            "trading_paused": risk.trading_paused,
            "reason": risk.reason,
            "margin_used": round(margin_used, 2),
            "margin_free": round(margin_free, 2),
            "margin_level_pct": round(margin_level_pct, 2),
            "margin_usage_pct": round(margin_usage_pct, 2),
            "total_open_risk_pct": total_open_risk_pct,
            "consecutive_losses": consecutive_losses,
            "max_consecutive_losses": 3,
            "max_risk_pct": max_risk_pct,
            "max_daily_drawdown_pct": max_daily_dd,
            "max_positions": max_positions,
            "avg_spread_pips": 1.2,
            "avg_rr_ratio": 1.5,
            "is_weekend": is_weekend,
        }


@risk_router.get("/api/risk/scorecard", tags=["Risk"])
@require_role(Role.VIEWER)
async def get_risk_scorecard(
    symbol: str = Query(default="EURUSD", description="Asset symbol to evaluate against risk gate"),
):
    """Evaluate 22-point deterministic Risk Gate rules scorecard for live telemetry."""
    from monika.core.config.settings import load_settings
    from monika.domain.risk.risk_gate import RiskGate
    from monika.infrastructure.database.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        settings = load_settings()
        risk_gate = RiskGate(settings=settings)
        return await risk_gate.get_current_scorecard(session=session, symbol=symbol.upper())


@risk_router.get("/api/risk/correlation-matrix", tags=["Risk"])
@require_role(Role.VIEWER)
async def get_risk_correlation_matrix():
    """Compute rolling cross-asset correlation matrix and aggregate portfolio heat score."""
    from sqlalchemy import select

    from monika.domain.risk.correlation_matrix import DynamicCorrelationMatrix
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import Position

    async with AsyncSessionLocal() as session:
        open_positions = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()

        pos_list = [
            {"symbol": p.symbol, "direction": p.direction, "volume": float(p.volume or 0.01)} for p in open_positions
        ]

        active_symbols = list({p.symbol.upper() for p in open_positions if p.symbol})
        default_symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
        for s in default_symbols:
            if s not in active_symbols:
                active_symbols.append(s)

        corr_engine = DynamicCorrelationMatrix()
        matrix = await corr_engine.get_matrix(session, active_symbols)
        heat = corr_engine.calculate_portfolio_heat(pos_list, matrix)

        return {
            "symbols": active_symbols,
            "matrix": matrix,
            "portfolio_heat": heat.get("portfolio_heat", 0.0),
            "status": heat.get("status", "normal"),
            "correlated_pairs": heat.get("correlated_pairs", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@risk_router.post("/api/actions/override-risk", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_override_risk(payload: OverrideRiskRequest, request: Request):
    """Update dynamic risk parameters in SystemConfig and runtime settings with duration support."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import ActivityLogRepository, SystemConfigRepository

    updated_fields = {}
    if payload.risk_percent_per_trade is not None:
        updated_fields["risk_percent_per_trade"] = float(payload.risk_percent_per_trade)
    if payload.max_daily_drawdown_percent is not None:
        updated_fields["max_daily_drawdown_percent"] = float(payload.max_daily_drawdown_percent)
    if payload.max_weekly_drawdown_percent is not None:
        updated_fields["max_weekly_drawdown_percent"] = float(payload.max_weekly_drawdown_percent)
    if payload.max_concurrent_positions is not None:
        updated_fields["max_concurrent_positions"] = int(payload.max_concurrent_positions)
    if payload.max_lot_per_symbol is not None:
        updated_fields["max_lot_per_symbol"] = float(payload.max_lot_per_symbol)
    if payload.max_risk_amount_usd is not None:
        updated_fields["max_risk_amount_usd"] = float(payload.max_risk_amount_usd)
    if payload.auto_execute is not None:
        updated_fields["auto_execute"] = bool(payload.auto_execute)
    if payload.system_paused is not None:
        updated_fields["system_paused"] = bool(payload.system_paused)
    if payload.custom_overrides:
        updated_fields.update(payload.custom_overrides)
    if payload.duration_seconds is not None and payload.duration_seconds > 0:
        exp = datetime.now(timezone.utc) + timedelta(seconds=payload.duration_seconds)
        updated_fields["expires_at"] = exp.isoformat()
    elif payload.expires_at is not None:
        updated_fields["expires_at"] = str(payload.expires_at)

    if not updated_fields:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "No risk fields provided to override."}
        )

    async with AsyncSessionLocal() as session:
        cfg_repo = SystemConfigRepository(session)
        act_repo = ActivityLogRepository(session)

        raw_val = await cfg_repo.get("risk_override")
        current_cfg = {}
        if raw_val:
            try:
                current_cfg = json.loads(raw_val)
            except Exception:
                pass
        current_cfg.update(updated_fields)
        await cfg_repo.set("risk_override", json.dumps(current_cfg), description="Dynamic risk override")

        settings = get_dashboard_dependency("settings")
        if settings and isinstance(settings, dict):
            trading_risk = settings.setdefault("trading", {}).setdefault("risk", {})
            trading_risk.update(updated_fields)

        reason_text = payload.reason or f"Risk parameters overridden via Dashboard: {list(updated_fields.keys())}"
        await act_repo.log_activity(
            category="risk",
            description=reason_text,
            actor="dashboard",
        )
        await session.commit()

    await broadcast_live_event(
        "risk_override_updated",
        {
            "updated_fields": updated_fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "status": "success",
        "message": "Risk parameters overridden successfully.",
        "updated": updated_fields,
        "effective_config": current_cfg,
    }
