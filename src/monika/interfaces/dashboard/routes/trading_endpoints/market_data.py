# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/market_data.py
# Description: Market candles, structural support/resistance levels, and indicator snapshots
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.indicators.technical import (
    CHART_WORKSPACE_PRESETS,
    evaluate_workspace_indicators,
    normalize_chart_workspace_config,
)
from monika.infrastructure.database.db import AsyncSessionLocal, get_db
from monika.infrastructure.database.models import (
    AssetAnalysis,
    FVGZone,
    LiquidityZone,
    OrderBlock,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    StructureBreak,
    TechnicalIndicator,
)
from monika.infrastructure.database.repositories.user_preference_repository import (
    CHART_WORKSPACE_CATEGORY,
    SqlAlchemyUserPreferenceRepository,
)
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
from monika.interfaces.dashboard.schemas import ChartConfigSaveRequest

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Market_data")

market_data_router = APIRouter()

_TF_DURATION_MAP: dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
    "MN1": 2592000,
}


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield database session for FastAPI dependency injection."""
    async for s in get_db():
        yield s


_DB_SESSION = Depends(get_db_session)


def _build_synthetic_preview_candles(
    sym: str,
    timeframe: str,
    count: int,
    base_price_override: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Build realistic synthetic preview OHLCV bars when broker/database bars are unavailable."""
    now_ts = int(time.time())
    step_sec = _TF_DURATION_MAP.get(timeframe.upper(), 14400)

    if base_price_override is not None and base_price_override > 0:
        base_price = float(base_price_override)
    else:
        base_price = (
            1.0850
            if "EUR" in sym
            else 1.2850
            if "GBP" in sym
            else 2650.0
            if "XAU" in sym
            else 67000.0
            if "BTC" in sym
            else 152.0
            if "JPY" in sym
            else 100.0
        )

    p = base_price
    start_ts = now_ts - (count * step_sec)
    candles: list[dict[str, Any]] = []
    for i in range(count):
        t = start_ts + (i * step_sec)
        noise = (math.sin(i * 0.18) + math.cos(i * 0.09)) * (base_price * 0.0012)
        drift = (i - count / 2) * (base_price * 0.00008)
        open_p = p
        close_p = p + noise + drift
        high_p = max(open_p, close_p) + abs(noise * 0.5)
        low_p = min(open_p, close_p) - abs(noise * 0.5)
        vol = abs(100.0 + math.sin(i * 0.5) * 50.0)
        candles.append(
            {
                "time": t,
                "open": round(open_p, 5),
                "high": round(high_p, 5),
                "low": round(low_p, 5),
                "close": round(close_p, 5),
                "volume": round(vol, 2),
            }
        )
        p = close_p
    return candles


@market_data_router.get("/api/v1/market/indicators/{symbol}", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_technical_indicators_snapshot(
    symbol: str,
    timeframe: str = Query(default="H1", description="Timeframe e.g. M15, H1, H4, D1"),
):
    """Retrieve computed technical indicators (MA, RSI, MACD, BB, ATR) for a symbol."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import TechnicalIndicator

    sym = symbol.strip().upper().replace("/", "")

    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == sym)
                    .where(TechnicalIndicator.timeframe == timeframe.upper())
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )

        indicators_map = {}
        for r in rows:
            if r.indicator_name not in indicators_map:
                try:
                    val = json.loads(r.value_json) if isinstance(r.value_json, str) else r.value_json
                except Exception:
                    val = r.value_json
                indicators_map[r.indicator_name] = {
                    "value": val,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }

        if not indicators_map:
            try:
                from monika.core.config.settings import load_settings
                from monika.application.services.technical_indicator_service import (
                    TechnicalIndicatorService as TechnicalIndicatorCalculator,
                )

                settings = load_settings() or {}
                calc = TechnicalIndicatorCalculator(session, settings)
                snapshot = await calc.get_snapshot(sym, timeframe.upper())
                if snapshot:
                    indicators_map = snapshot
            except Exception as e:
                logger.debug(f"Indicator calculation on the fly failed for {sym}: {e}")

        return {
            "symbol": sym,
            "timeframe": timeframe.upper(),
            "indicators": indicators_map,
            "total_indicators": len(indicators_map),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@market_data_router.get("/api/v1/market/structure/{symbol}", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_market_structure_levels(
    symbol: str,
    timeframe: str = Query(default="H4", description="Timeframe e.g. M15, H1, H4, D1"),
):
    """Retrieve SMC market structure levels: Order Blocks, FVGs, and Structure Breaks."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import FVGZone, OrderBlock, StructureBreak

    sym = symbol.strip().upper().replace("/", "")

    async with AsyncSessionLocal() as session:
        ob_rows = (
            (
                await session.execute(
                    select(OrderBlock)
                    .where(OrderBlock.symbol == sym)
                    .where(OrderBlock.timeframe == timeframe.upper())
                    .where(OrderBlock.mitigated_at.is_(None))
                    .order_by(OrderBlock.formed_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

        sb_rows = (
            (
                await session.execute(
                    select(StructureBreak)
                    .where(StructureBreak.symbol == sym)
                    .where(StructureBreak.timeframe == timeframe.upper())
                    .order_by(StructureBreak.formed_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

        fvg_rows = (
            (
                await session.execute(
                    select(FVGZone)
                    .where(FVGZone.symbol == sym)
                    .where(FVGZone.timeframe == timeframe.upper())
                    .where(FVGZone.filled_at.is_(None))
                    .order_by(FVGZone.formed_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

        timesfm_cone = None
        try:
            from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

            engine = TimesFMEngine()
            fc = await engine.get_latest_forecast(session, sym, timeframe=timeframe.upper())
            if fc and isinstance(fc, dict):
                timesfm_cone = {
                    "generated_at": fc.get("generated_at"),
                    "quantiles": fc.get("quantiles", {}),
                    "reachability_envelope": fc.get("reachability_envelope", []),
                    "horizon_steps": fc.get("horizon_steps", 12),
                    "drift": fc.get("drift", 0.0),
                }
        except Exception:
            pass

        return {
            "symbol": sym,
            "timeframe": timeframe.upper(),
            "order_blocks": [
                {
                    "id": ob.id,
                    "direction": ob.direction,
                    "price_high": ob.price_high,
                    "price_low": ob.price_low,
                    "formed_at": ob.formed_at.isoformat() if ob.formed_at else None,
                }
                for ob in ob_rows
            ],
            "structure_breaks": [
                {
                    "id": sb.id,
                    "type": sb.type,
                    "direction": sb.direction,
                    "price": sb.price,
                    "formed_at": sb.formed_at.isoformat() if sb.formed_at else None,
                }
                for sb in sb_rows
            ],
            "fair_value_gaps": [
                {
                    "id": f.id,
                    "direction": f.direction,
                    "gap_high": f.gap_high,
                    "gap_low": f.gap_low,
                    "formed_at": f.formed_at.isoformat() if f.formed_at else None,
                }
                for f in fvg_rows
            ],
            "timesfm_cone": timesfm_cone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@market_data_router.get("/api/v1/market/candles/{symbol}", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_market_candles(
    symbol: str,
    timeframe: str = Query(default="H4", description="Timeframe e.g. M15, H1, H4, D1"),
    count: int = Query(default=150, ge=10, le=1000),
):
    """Retrieve OHLCV candlestick bars for financial Canvas charts."""
    sym = symbol.strip().upper().replace("/", "")
    mt5_client = get_dashboard_dependency("mt5_client")

    candles: List[Dict[str, Any]] = []
    if mt5_client and hasattr(mt5_client, "get_ohlcv"):
        try:
            df = await mt5_client.get_ohlcv(sym, timeframe=timeframe.upper(), count=count)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    raw_time = row.get("time")
                    t_val = int(raw_time.timestamp()) if hasattr(raw_time, "timestamp") else int(raw_time)
                    candles.append(
                        {
                            "time": t_val,
                            "open": float(row.get("open", 0.0)),
                            "high": float(row.get("high", 0.0)),
                            "low": float(row.get("low", 0.0)),
                            "close": float(row.get("close", 0.0)),
                            "volume": float(row.get("tick_volume", row.get("volume", 0.0))),
                        }
                    )
        except Exception as e:
            logger.debug(f"Live candle fetch for {sym} failed: {e}")

    is_synthetic = False
    if not candles:
        is_synthetic = True
        logger.warning(
            f"[MarketData] Broker candles unavailable for {sym} ({timeframe}). Providing preview bars (is_synthetic=True)."
        )
        base_override = None
        if mt5_client and hasattr(mt5_client, "get_current_price"):
            try:
                curr_quote = await mt5_client.get_current_price(sym)
                if curr_quote and curr_quote.get("bid"):
                    base_override = float(curr_quote["bid"])
            except Exception:
                pass
        candles = _build_synthetic_preview_candles(sym, timeframe, count, base_override)

    return {
        "symbol": sym,
        "timeframe": timeframe.upper(),
        "count": len(candles),
        "is_synthetic": is_synthetic,
        "candles": candles,
    }


# ==============================================================================
# Institutional Chart Workspace & Indicator Studio Endpoints
# ==============================================================================


@market_data_router.get("/api/v1/market/chart-config", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_chart_workspace_config_bundle(
    request: Request,
    session: AsyncSession = _DB_SESSION,
) -> dict[str, Any]:
    """Retrieve saved global and per-symbol chart workspace configurations with preset definitions."""
    repo = SqlAlchemyUserPreferenceRepository(session)
    bundle = await repo.get_chart_workspace_bundle()
    return {
        "global": bundle["global"],
        "symbols": bundle["symbols"],
        "presets": CHART_WORKSPACE_PRESETS,
        "updated_at": datetime.now(UTC).isoformat(),
    }


@market_data_router.put("/api/v1/market/chart-config", tags=["Market Data"])
@require_role(Role.VIEWER)
async def save_chart_workspace_config(
    payload: ChartConfigSaveRequest,
    request: Request,
    session: AsyncSession = _DB_SESSION,
) -> dict[str, Any]:
    """Save or update chart workspace configuration at global or per-symbol scope."""
    norm_cfg = normalize_chart_workspace_config(payload.config)
    key = payload.symbol.strip().upper() if payload.scope == "symbol" and payload.symbol else "global"
    repo = SqlAlchemyUserPreferenceRepository(session)
    await repo.set_preference(CHART_WORKSPACE_CATEGORY, key, norm_cfg)
    await session.commit()
    return {
        "status": "ok",
        "scope": payload.scope,
        "symbol": key if key != "global" else None,
        "config": norm_cfg,
    }


@market_data_router.delete("/api/v1/market/chart-config/{symbol}", tags=["Market Data"])
@require_role(Role.VIEWER)
async def delete_chart_workspace_override(
    symbol: str,
    request: Request,
    session: AsyncSession = _DB_SESSION,
) -> dict[str, Any]:
    """Remove symbol-specific chart workspace layout override to revert to global layout."""
    sym_clean = symbol.strip().upper().replace("/", "")
    repo = SqlAlchemyUserPreferenceRepository(session)
    await repo.delete_preference(CHART_WORKSPACE_CATEGORY, sym_clean)
    await session.commit()
    return {"status": "ok", "symbol": sym_clean}


@market_data_router.get("/api/v1/market/chart-workspace/{symbol}", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_chart_workspace(
    symbol: str,
    request: Request,
    timeframe: Optional[str] = Query(default=None, description="Timeframe e.g. M15, H1, H4, D1"),
    count: int = Query(default=250, ge=10, le=1000),
    session: AsyncSession = _DB_SESSION,
) -> dict[str, Any]:
    """
    Unified institutional chart workspace payload combining candles, technical indicator series,
    pivot points, alignment summary, SMC market structures, active positions, and AI proposals.
    """
    sym = symbol.strip().upper().replace("/", "")
    repo = SqlAlchemyUserPreferenceRepository(session)
    workspace_config = await repo.resolve_chart_workspace_config(sym)

    tf = (timeframe or workspace_config.get("timeframe") or "H4").strip().upper()
    if tf not in _TF_DURATION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{tf}'. Supported timeframes: {', '.join(_TF_DURATION_MAP.keys())}",
        )

    workspace_config = {**workspace_config, "timeframe": tf}

    # Fetch historical bars with warm-up buffer for technical indicators
    fetch_count = min(1000, count + 220)
    mt5_client = get_dashboard_dependency("mt5_client")
    candles: list[dict[str, Any]] = []
    source = "live_broker"

    if mt5_client and hasattr(mt5_client, "get_ohlcv"):
        try:
            df_broker = await mt5_client.get_ohlcv(sym, timeframe=tf, count=fetch_count)
            if df_broker is not None and not df_broker.empty:
                for _, row in df_broker.iterrows():
                    raw_time = row.get("time")
                    t_val = int(raw_time.timestamp()) if hasattr(raw_time, "timestamp") else int(raw_time)
                    candles.append(
                        {
                            "time": t_val,
                            "open": float(row.get("open", 0.0)),
                            "high": float(row.get("high", 0.0)),
                            "low": float(row.get("low", 0.0)),
                            "close": float(row.get("close", 0.0)),
                            "volume": float(row.get("tick_volume", row.get("volume", 0.0))),
                        }
                    )
        except Exception as e:
            logger.debug(f"Broker candle fetch for {sym} failed: {e}")

    if not candles:
        stmt_ohlcv = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == sym)
            .where(PriceOHLCV.timeframe == tf)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(fetch_count)
        )
        res_ohlcv = await session.execute(stmt_ohlcv)
        db_rows = list(reversed(res_ohlcv.scalars().all()))
        if db_rows:
            source = "database"
            for r in db_rows:
                ts = getattr(r, "canonical_timestamp", None) or getattr(r, "timestamp", None)
                if ts is not None and hasattr(ts, "timestamp"):
                    t_val = int(ts.timestamp())
                elif ts is not None:
                    try:
                        t_val = int(ts)
                    except ValueError, TypeError:
                        t_val = 0
                else:
                    t_val = 0
                candles.append(
                    {
                        "time": t_val,
                        "open": float(r.open),
                        "high": float(r.high),
                        "low": float(r.low),
                        "close": float(r.close),
                        "volume": float(r.volume or 0.0),
                    }
                )

    if not candles:
        source = "synthetic"
        base_override = None
        if mt5_client and hasattr(mt5_client, "get_current_price"):
            try:
                curr_quote = await mt5_client.get_current_price(sym)
                if curr_quote and curr_quote.get("bid"):
                    base_override = float(curr_quote["bid"])
            except Exception:
                pass
        candles = _build_synthetic_preview_candles(sym, tf, fetch_count, base_override)

    visible_candles = candles[-count:]

    # Evaluate indicators on full series for warm-up, returning last `count` bars
    full_df = pd.DataFrame(
        [
            {
                "timestamp": c["time"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            }
            for c in candles
        ]
    )
    eval_res = await asyncio.to_thread(evaluate_workspace_indicators, full_df, workspace_config, count)

    # SMC market structure queries
    ob_rows = (
        (
            await session.execute(
                select(OrderBlock)
                .where(OrderBlock.symbol == sym)
                .where(OrderBlock.timeframe == tf)
                .where(OrderBlock.mitigated_at.is_(None))
                .order_by(OrderBlock.formed_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    sb_rows = (
        (
            await session.execute(
                select(StructureBreak)
                .where(StructureBreak.symbol == sym)
                .where(StructureBreak.timeframe == tf)
                .order_by(StructureBreak.formed_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    fvg_rows = (
        (
            await session.execute(
                select(FVGZone)
                .where(FVGZone.symbol == sym)
                .where(FVGZone.timeframe == tf)
                .where(FVGZone.filled_at.is_(None))
                .order_by(FVGZone.formed_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    liq_rows = (
        (
            await session.execute(
                select(LiquidityZone)
                .where(LiquidityZone.symbol == sym)
                .where(LiquidityZone.timeframe == tf)
                .order_by(LiquidityZone.identified_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    timesfm_cone = None
    try:
        from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

        engine = TimesFMEngine()
        fc = await engine.get_latest_forecast(session, sym, timeframe=tf)
        if fc and isinstance(fc, dict):
            timesfm_cone = {
                "generated_at": fc.get("generated_at"),
                "quantiles": fc.get("quantiles", {}),
                "reachability_envelope": fc.get("reachability_envelope", []),
                "horizon_steps": fc.get("horizon_steps", 12),
                "drift": fc.get("drift", 0.0),
            }
    except Exception:
        pass

    structure_breaks_list = [
        {
            "id": sb.id,
            "type": sb.type,
            "direction": sb.direction,
            "price": float(sb.price),
            "time": int(sb.formed_at.timestamp()) if sb.formed_at and hasattr(sb.formed_at, "timestamp") else None,
            "formed_at": sb.formed_at.isoformat() if sb.formed_at else None,
        }
        for sb in sb_rows
    ]

    liquidity_zones_list = [
        {
            "id": lq.id,
            "type": lq.type,
            "price": round((float(lq.zone_high) + float(lq.zone_low)) / 2.0, 5),
            "zone_high": float(lq.zone_high),
            "zone_low": float(lq.zone_low),
            "identified_at": lq.identified_at.isoformat() if lq.identified_at else None,
        }
        for lq in liq_rows
    ]

    structure_payload = {
        "order_blocks": [
            {
                "id": ob.id,
                "direction": ob.direction,
                "type": ob.direction,
                "price_high": float(ob.price_high),
                "price_low": float(ob.price_low),
                "top": float(ob.price_high),
                "bottom": float(ob.price_low),
                "formed_at": ob.formed_at.isoformat() if ob.formed_at else None,
            }
            for ob in ob_rows
        ],
        "structure_breaks": structure_breaks_list,
        "breaks": structure_breaks_list,
        "fair_value_gaps": [
            {
                "id": f.id,
                "direction": f.direction,
                "type": f.direction,
                "gap_high": float(f.gap_high),
                "gap_low": float(f.gap_low),
                "top": float(f.gap_high),
                "bottom": float(f.gap_low),
                "formed_at": f.formed_at.isoformat() if f.formed_at else None,
            }
            for f in fvg_rows
        ],
        "liquidity_zones": liquidity_zones_list,
        "liquidity_pools": liquidity_zones_list,
        "timesfm_cone": timesfm_cone,
        "timesfm": timesfm_cone,
    }

    # Query active open positions
    active_positions: list[dict[str, Any]] = []
    seen_tickets: set[int] = set()

    pos_rows = (
        (
            await session.execute(
                select(Position)
                .where(Position.symbol == sym)
                .where(Position.status.ilike("open"))
                .order_by(Position.opened_at.desc())
            )
        )
        .scalars()
        .all()
    )

    for p in pos_rows:
        ticket = p.mt5_ticket or p.id
        seen_tickets.add(ticket)
        sl_v = float(p.sl) if p.sl is not None else None
        tp_v = float(p.tp) if p.tp is not None else None
        pnl_v = float(p.pnl) if p.pnl is not None else 0.0
        active_positions.append(
            {
                "id": p.id,
                "ticket": ticket,
                "symbol": sym,
                "direction": (p.direction or "BUY").lower(),
                "volume": float(p.volume),
                "entry_price": float(p.entry_price),
                "sl": sl_v,
                "tp": tp_v,
                "stop_loss": sl_v,
                "take_profit": tp_v,
                "pnl": pnl_v,
                "unrealized_pnl": pnl_v,
            }
        )

    paper_rows = (
        (
            await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == sym)
                .where(PaperTradeRecord.status.ilike("open"))
                .order_by(PaperTradeRecord.opened_at.desc())
            )
        )
        .scalars()
        .all()
    )

    for pt in paper_rows:
        ticket = pt.id
        if ticket in seen_tickets:
            continue
        sl_v = float(pt.stop_loss) if pt.stop_loss is not None else None
        tp_v = float(pt.take_profit) if pt.take_profit is not None else None
        pnl_v = float(pt.pnl_pct or 0.0)
        active_positions.append(
            {
                "id": pt.id,
                "ticket": ticket,
                "symbol": sym,
                "direction": (pt.direction or "BUY").lower(),
                "volume": float(pt.requested_lot or 0.01),
                "entry_price": float(pt.entry_price),
                "sl": sl_v,
                "tp": tp_v,
                "stop_loss": sl_v,
                "take_profit": tp_v,
                "pnl": pnl_v,
                "unrealized_pnl": pnl_v,
            }
        )

    # Query latest AI proposal
    stmt_act = (
        select(AssetAnalysis)
        .where(AssetAnalysis.symbol == sym)
        .where(AssetAnalysis.decision.in_(["buy", "sell", "BUY", "SELL"]))
        .order_by(AssetAnalysis.generated_at.desc())
        .limit(1)
    )
    res_act = await session.execute(stmt_act)
    latest_row = res_act.scalar_one_or_none()

    if latest_row is None:
        stmt_any = (
            select(AssetAnalysis)
            .where(AssetAnalysis.symbol == sym)
            .order_by(AssetAnalysis.generated_at.desc())
            .limit(1)
        )
        res_any = await session.execute(stmt_any)
        latest_row = res_any.scalar_one_or_none()

    latest_ai_proposal: Optional[dict[str, Any]] = None
    if latest_row is not None:
        ts = getattr(latest_row, "timestamp", None) or getattr(latest_row, "generated_at", None)
        act = getattr(latest_row, "proposed_action", None) or getattr(latest_row, "decision", None) or "HOLD"
        entry_val: Optional[float] = None
        raw_entry_attr = getattr(latest_row, "entry_price", None)
        if isinstance(raw_entry_attr, (int, float)):
            entry_val = float(raw_entry_attr)
        elif getattr(latest_row, "entry_zone", None):
            try:
                ez = json.loads(str(latest_row.entry_zone))
                if isinstance(ez, dict) and isinstance(ez.get("price"), (int, float)):
                    entry_val = float(ez["price"])
            except Exception:
                pass
        raw_paa = getattr(latest_row, "price_at_analysis", None)
        if entry_val is None and isinstance(raw_paa, (int, float)):
            entry_val = float(raw_paa)
        sl_v = float(latest_row.stop_loss) if latest_row.stop_loss is not None else None
        tp_v = float(latest_row.take_profit) if latest_row.take_profit is not None else None
        latest_ai_proposal = {
            "analysis_id": latest_row.id,
            "symbol": sym,
            "decision": str(act).lower(),
            "action": str(act).upper(),
            "entry_price": entry_val,
            "sl": sl_v,
            "tp": tp_v,
            "stop_loss": sl_v,
            "take_profit": tp_v,
            "confidence": float(latest_row.confidence) if latest_row.confidence is not None else None,
            "confluence_score": int(latest_row.confluence_score) if latest_row.confluence_score is not None else None,
            "generated_at": ts.isoformat() if ts is not None else None,
            "created_at": ts.isoformat() if ts is not None else None,
        }

    return {
        "symbol": sym,
        "timeframe": tf,
        "count": len(visible_candles),
        "source": source,
        "workspace_config": eval_res["workspace_config"],
        "config": eval_res["workspace_config"],
        "candles": visible_candles,
        "indicator_series": eval_res["series"],
        "indicators": eval_res["series"],
        "pivot_points": eval_res["pivot_points"],
        "indicator_summary": {
            **eval_res["summary"],
            "_overall": eval_res["overall"],
        },
        "structure": structure_payload,
        "active_positions": active_positions,
        "positions": active_positions,
        "latest_ai_proposal": latest_ai_proposal,
        "ai_proposals": [latest_ai_proposal] if latest_ai_proposal else [],
    }
