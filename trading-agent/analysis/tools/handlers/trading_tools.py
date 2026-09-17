"""
Trading execution and submission tool handlers and self-registration.
Direct execution without circular trampolines.
"""

import json
import logging
from typing import Any, Dict, Optional
from analysis.tools.registry import ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.Tools.Trading")


async def handle_submit_asset_analysis(args: dict, **ctx) -> dict:
    from analysis.tools.handlers.analysis_submit import handle_submit_asset_analysis as _submit_asset
    session = ctx.get("session") or getattr(ctx.get("executor"), "session", None)
    return await _submit_asset(args, session=session, executor=ctx.get("executor"))


async def handle_submit_fundamental_brief(args: dict, **ctx) -> dict:
    from analysis.tools.handlers.analysis_submit import handle_submit_fundamental_brief as _submit_brief
    session = ctx.get("session") or getattr(ctx.get("executor"), "session", None)
    return await _submit_brief(args, session=session, executor=ctx.get("executor"))


async def handle_get_open_positions(args: dict, **ctx) -> Any:
    from analysis.tools.handlers.position_mgmt import handle_get_open_positions as _get_pos
    session = ctx.get("session") or getattr(ctx.get("executor"), "session", None)
    return await _get_pos(session=session, **args)


async def handle_get_trade_history(args: dict, **ctx) -> dict:
    from analysis.tools.handlers.trade_intel import handle_get_trade_history as _get_history
    session = ctx.get("session") or getattr(ctx.get("executor"), "session", None)
    return await _get_history(args, session=session, executor=ctx.get("executor"))


async def handle_calculate_position_size(args: dict, **ctx) -> dict:
    from analysis.tools.handlers.position_mgmt import handle_calculate_position_size as _calc_size
    session = ctx.get("session") or getattr(ctx.get("executor"), "session", None)
    return await _calc_size(args, session=session, executor=ctx.get("executor"))


def register_trading_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="submit_asset_analysis",
            description="Submit formal trading decision and setup parameters for an asset (Stage 2 output).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "decision": {"type": "string"}}},
            handler=handle_submit_asset_analysis,
            toolset="trading",
            requires_db=True,
        ),
        ToolDefinition(
            name="submit_fundamental_brief",
            description="Submit macroeconomic analysis and currency biases (Stage 1 output).",
            parameters={"type": "object", "properties": {"macro_regime": {"type": "string"}}},
            handler=handle_submit_fundamental_brief,
            toolset="trading",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_open_positions",
            description="Fetch all active open trading positions from MT5.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_open_positions,
            toolset="trading",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_trade_history",
            description="Fetch recent closed paper and live trading history.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}}},
            handler=handle_get_trade_history,
            toolset="trading",
            requires_db=True,
        ),
        ToolDefinition(
            name="calculate_position_size",
            description="Calculate risk-adjusted position lot size for a setup.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "entry_price": {"type": "number"}, "stop_loss": {"type": "number"}}},
            handler=handle_calculate_position_size,
            toolset="trading",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


register_trading_tools()
