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
    rows = (await session.execute(
        select(OrderBlock)
        .where(OrderBlock.symbol == symbol)
        .where(OrderBlock.timeframe == timeframe)
        .where(OrderBlock.mitigated_at == None)
        .order_by(OrderBlock.formed_at.desc())
        .limit(10)
    )).scalars().all()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
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

    try:
        from analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep
        return await detect_liquidity_sweep(session, symbol, settings)
    except Exception as e:
        logger.debug(f"[{symbol}] Liquidity sweep detection error: {e}")
        return {"symbol": symbol, "status": "unavailable", "error": str(e)}


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
    ]
    for t in tools:
        registry.register(t)


register_smc_tools()
