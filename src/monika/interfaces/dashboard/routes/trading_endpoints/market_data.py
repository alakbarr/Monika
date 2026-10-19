# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/market_data.py
# Description: Market candles, structural support/resistance levels, and indicator snapshots
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

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Market_data")

market_data_router = APIRouter()


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
                from monika.domain.indicators.technical import TechnicalIndicatorCalculator

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
        import math
        import time

        now_ts = int(time.time())
        step_map = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
        step_sec = step_map.get(timeframe.upper(), 14400)

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
        if mt5_client and hasattr(mt5_client, "get_current_price"):
            try:
                curr_quote = await mt5_client.get_current_price(sym)
                if curr_quote and curr_quote.get("bid"):
                    base_price = float(curr_quote["bid"])
            except Exception:
                pass

        p = base_price
        start_ts = now_ts - (count * step_sec)
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

    return {
        "symbol": sym,
        "timeframe": timeframe.upper(),
        "count": len(candles),
        "is_synthetic": is_synthetic,
        "candles": candles,
    }
