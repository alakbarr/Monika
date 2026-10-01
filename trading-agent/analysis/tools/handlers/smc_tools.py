"""
Smart Money Concepts (SMC) tool handlers and self-registration.
Handles Order Blocks (OB), Fair Value Gaps (FVG), Liquidity pools, Volume Profiles, and Liquidity Sweeps.
Direct execution without circular trampolines.
"""

import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import OrderBlock, FVGZone, LiquidityZone
from analysis.tools.registry import ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.Tools.SMC")


def _get_session_and_symbol(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], Optional[str], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    if not sym:
        sym = args.get("symbol") or getattr(executor, "symbol", None)
    if sym and isinstance(sym, str):
        sym = sym.strip().upper().replace("/", "")
    return session, sym, settings


async def handle_get_order_blocks(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_order_blocks"}

    timeframe = args.get("timeframe", "H4")
    days = int(args.get("days", args.get("lookback_days", 14)))
    limit = int(args.get("limit", 10))

    stmt = (
        select(OrderBlock)
        .where(OrderBlock.symbol == symbol)
        .where(OrderBlock.timeframe == timeframe)
        .where(OrderBlock.mitigated_at == None)
    )
    if days > 0:
        import utils.clock as clock
        from datetime import timedelta
        cutoff = clock.now() - timedelta(days=days)
        stmt = stmt.where(OrderBlock.formed_at >= cutoff)

    rows = (await session.execute(stmt.order_by(OrderBlock.formed_at.desc()).limit(limit))).scalars().all()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "lookback_days": days,
        "count": len(rows),
        "order_blocks": [
            {
                "price_high": r.price_high,
                "price_low": r.price_low,
                "direction": r.direction,
                "formed_at": r.formed_at.isoformat() if hasattr(r.formed_at, "isoformat") else str(r.formed_at),
            }
            for r in rows
        ],
    }


async def handle_get_fvg_zones(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_fvg_zones"}

    timeframe = args.get("timeframe", "H4")
    include_filled = args.get("filled", False)

    query = (
        select(FVGZone)
        .where(FVGZone.symbol == symbol)
        .where(FVGZone.timeframe == timeframe)
        .order_by(FVGZone.formed_at.desc())
        .limit(30)
    )
    if not include_filled:
        query = query.where(FVGZone.filled_at == None)

    rows = (await session.execute(query)).scalars().all()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(rows),
        "fvg_zones": [
            {
                "gap_high": r.gap_high,
                "gap_low": r.gap_low,
                "direction": r.direction,
                "formed_at": r.formed_at.isoformat() if hasattr(r.formed_at, "isoformat") else str(r.formed_at),
                "filled_at": r.filled_at.isoformat() if r.filled_at and hasattr(r.filled_at, "isoformat") else (str(r.filled_at) if r.filled_at else None),
                "status": "unfilled" if r.filled_at is None else "filled",
            }
            for r in rows
        ],
    }


async def handle_get_liquidity_zones(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_liquidity_zones"}

    timeframe = args.get("timeframe", "H4")
    rows = (await session.execute(
        select(LiquidityZone)
        .where(LiquidityZone.symbol == symbol)
        .where(LiquidityZone.timeframe == timeframe)
        .order_by(LiquidityZone.identified_at.desc())
        .limit(20)
    )).scalars().all()

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(rows),
        "zones": [
            {
                "zone_high": r.zone_high,
                "zone_low": r.zone_low,
                "type": r.type,
                "label": "BSL" if "above" in str(r.type).lower() or "high" in str(r.type).lower() else "SSL",
                "side": "BSL" if "above" in str(r.type).lower() or "high" in str(r.type).lower() else "SSL",
                "tag": "BSL (Buy-side Liquidity)" if "above" in str(r.type).lower() or "high" in str(r.type).lower() else "SSL (Sell-side Liquidity)",
                "identified_at": r.identified_at.isoformat() if hasattr(r.identified_at, "isoformat") else str(r.identified_at),
            }
            for r in rows
        ],
    }


async def handle_get_volume_profile(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for volume profile"}

    try:
        from analysis.calculators.volume_profile import compute_volume_profile, compute_anchored_vwap
        vp = await compute_volume_profile(session, symbol, settings)
        vwap = await compute_anchored_vwap(session, symbol)
        return {"symbol": symbol, "volume_profile": vp, "anchored_vwap": vwap}
    except Exception as e:
        logger.debug(f"[{symbol}] Volume profile computation fallback: {e}")
        return {"symbol": symbol, "volume_profile": {}, "anchored_vwap": None, "note": str(e)}


async def handle_get_volume_profile_context(args: dict, **ctx) -> dict:
    return await handle_get_volume_profile(args, **ctx)


async def handle_get_liquidity_sweep_context(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for liquidity sweep"}

    timeframe = args.get("timeframe", "H1")
    mode = args.get("mode", "auto")

    try:
        from analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep
        return await detect_liquidity_sweep(session, symbol, settings, timeframe=timeframe, mode=mode)
    except Exception as e:
        logger.debug(f"[{symbol}] Liquidity sweep detection error: {e}")
        return {"symbol": symbol, "timeframe": timeframe, "status": "unavailable", "error": str(e)}


async def handle_get_inducements(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_inducements"}

    timeframe = args.get("timeframe", "M15")
    trend = args.get("trend", "bullish")

    try:
        from database.models import PriceOHLCV, SwingPoint
        from indicators.smc_advanced import detect_inducement

        # Fetch recent candles
        bars = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(100)
        )).scalars().all()
        if not bars:
            return {"symbol": symbol, "timeframe": timeframe, "idm_detected": False, "note": "Insufficient candle data"}

        bars_sorted = list(reversed(bars))
        df = pd.DataFrame([{
            "timestamp": b.timestamp,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume or 0)
        } for b in bars_sorted])

        # Fetch recent swing points
        swings_db = (await session.execute(
            select(SwingPoint)
            .where(SwingPoint.symbol == symbol, SwingPoint.timeframe == timeframe)
            .order_by(SwingPoint.timestamp.desc())
            .limit(20)
        )).scalars().all()

        swings = [{
            "timestamp": s.timestamp,
            "type": s.type,
            "price": float(s.price)
        } for s in reversed(swings_db)]

        res = detect_inducement(df, swings, trend=trend)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "trend": trend,
            "idm_detected": res.idm_detected,
            "idm_price": res.idm_price,
            "idm_time": res.idm_time,
            "is_swept": res.is_swept,
            "sweep_time": res.sweep_time,
            "valid_ob_low": res.valid_ob_low,
            "valid_ob_high": res.valid_ob_high,
            "details": res.details,
        }
    except Exception as e:
        logger.debug(f"[{symbol}] Inducement error: {e}")
        return {"symbol": symbol, "timeframe": timeframe, "error": str(e)}


async def handle_get_breaker_blocks(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_breaker_blocks"}

    timeframe = args.get("timeframe", "H4")

    try:
        from database.models import PriceOHLCV, OrderBlock
        from indicators.smc_advanced import detect_breaker_blocks

        bars = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(150)
        )).scalars().all()
        if not bars:
            return {"symbol": symbol, "timeframe": timeframe, "breakers": []}

        df = pd.DataFrame([{
            "timestamp": b.timestamp,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume or 0)
        } for b in reversed(bars)])

        obs_db = (await session.execute(
            select(OrderBlock)
            .where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe)
            .order_by(OrderBlock.formed_at.desc())
            .limit(30)
        )).scalars().all()

        obs = [{
            "price_high": float(o.price_high),
            "price_low": float(o.price_low),
            "direction": str(o.direction),
            "formed_at": o.formed_at.isoformat() if hasattr(o.formed_at, "isoformat") else str(o.formed_at)
        } for o in obs_db]

        breakers = detect_breaker_blocks(df, obs)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(breakers),
            "breakers": [
                {
                    "direction": b.direction,
                    "price_low": b.price_low,
                    "price_high": b.price_high,
                    "broken_at": b.broken_at,
                    "retested": b.retested,
                    "strength": b.strength
                }
                for b in breakers
            ]
        }
    except Exception as e:
        logger.debug(f"[{symbol}] Breaker block error: {e}")
        return {"symbol": symbol, "timeframe": timeframe, "error": str(e)}


async def handle_get_judas_swing(args: dict, **ctx) -> dict:
    session, symbol, settings = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_judas_swing"}

    timeframe = args.get("timeframe", "M15")

    try:
        from database.models import PriceOHLCV
        from indicators.smc_advanced import detect_judas_swing
        from analysis.calculators.liquidity_sweep_detector import _get_asian_session_range

        asian_range = await _get_asian_session_range(session, symbol, settings)
        if not asian_range:
            return {"symbol": symbol, "judas_detected": False, "note": "Asian session range unavailable"}

        bars = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(60)
        )).scalars().all()

        if not bars:
            return {"symbol": symbol, "judas_detected": False, "note": "Insufficient candle data"}

        df = pd.DataFrame([{
            "timestamp": b.timestamp,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume or 0)
        } for b in reversed(bars)])

        res = detect_judas_swing(
            df_m15=df,
            asian_high=asian_range.get("asian_high", 0.0),
            asian_low=asian_range.get("asian_low", 0.0)
        )
        return {
            "symbol": symbol,
            "judas_detected": res.judas_detected,
            "trap_direction": res.trap_direction,
            "expansion_extreme": res.expansion_extreme,
            "rejection_ratio": res.rejection_ratio,
            "asian_high": res.asian_high,
            "asian_low": res.asian_low,
            "timestamp": res.timestamp,
            "details": res.details
        }
    except Exception as e:
        logger.debug(f"[{symbol}] Judas swing error: {e}")
        return {"symbol": symbol, "error": str(e)}


async def handle_get_equal_highs_lows(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_equal_highs_lows"}

    timeframe = args.get("timeframe", "H1")
    tolerance_pips = float(args.get("tolerance_pips", 3.0))

    try:
        from database.models import PriceOHLCV
        from indicators.smc_advanced import detect_equal_highs_lows

        bars = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(150)
        )).scalars().all()
        if not bars:
            return {"symbol": symbol, "timeframe": timeframe, "pools": []}

        df = pd.DataFrame([{
            "timestamp": b.timestamp,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume or 0)
        } for b in reversed(bars)])

        pools = detect_equal_highs_lows(df, tolerance_pips=tolerance_pips)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(pools),
            "pools": [
                {
                    "pool_type": p.pool_type,
                    "price_level": p.price_level,
                    "touch_count": p.touch_count,
                    "tolerance_pips": p.tolerance_pips,
                    "swing_times": p.swing_times,
                    "is_swept": p.is_swept
                }
                for p in pools
            ]
        }
    except Exception as e:
        logger.debug(f"[{symbol}] EQH/EQL error: {e}")
        return {"symbol": symbol, "timeframe": timeframe, "error": str(e)}


async def handle_get_wick_to_wick_fvg(args: dict, **ctx) -> dict:
    session, symbol, _ = _get_session_and_symbol(args, ctx)
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    if not session:
        return {"status": "unavailable", "message": "Database session required for get_wick_to_wick_fvg"}

    timeframe = args.get("timeframe", "H4")

    try:
        from database.models import PriceOHLCV
        from indicators.smc_advanced import find_wick_to_wick_fvg

        bars = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(100)
        )).scalars().all()
        if not bars:
            return {"symbol": symbol, "timeframe": timeframe, "wick_fvgs": []}

        df = pd.DataFrame([{
            "timestamp": b.timestamp,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume or 0)
        } for b in reversed(bars)])

        wick_fvgs = find_wick_to_wick_fvg(df, timeframe=timeframe)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(wick_fvgs),
            "wick_fvgs": wick_fvgs
        }
    except Exception as e:
        logger.debug(f"[{symbol}] Wick-to-wick FVG error: {e}")
        return {"symbol": symbol, "timeframe": timeframe, "error": str(e)}


def register_smc_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_order_blocks",
            description="Fetch active institutional order blocks for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_order_blocks,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fvg_zones",
            description="Fetch unmitigated Fair Value Gaps (FVG) and imbalance zones.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_fvg_zones,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_liquidity_zones",
            description="Fetch liquidity pools (equal highs, equal lows, buy/sell stops).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_liquidity_zones,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_volume_profile",
            description="Fetch Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_volume_profile,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_volume_profile_context",
            description="Fetch volume profile and anchored VWAP context.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_volume_profile_context,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_liquidity_sweep_context",
            description="Detect recent liquidity sweeps for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_liquidity_sweep_context,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_inducements",
            description="Detect Inducement (IDM) price level and validation status.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_inducements,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_breaker_blocks",
            description="Detect Breaker Blocks formed by failed order blocks with polarity inversion.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_breaker_blocks,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_judas_swing",
            description="Detect London Open (08:00 UTC) Judas Swing false breakout trap.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_judas_swing,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_equal_highs_lows",
            description="Detect Equal Highs (EQH) and Equal Lows (EQL) engineered liquidity pools.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_equal_highs_lows,
            toolset="smc",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_wick_to_wick_fvg",
            description="Detect wick-to-wick shadow Fair Value Gaps on higher timeframes.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_wick_to_wick_fvg,
            toolset="smc",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


register_smc_tools()
