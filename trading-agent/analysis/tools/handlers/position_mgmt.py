# ==============================================================================
# File: analysis/tools/handlers/position_mgmt.py
# ==============================================================================

"""
Position management and execution proposal handlers.
Direct execution without circular trampolines.
"""

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from analysis.tools.domain.position_handlers import PositionToolHandlers
from analysis.tools.domain.execution_handlers import ExecutionToolHandlers
from database.models import ActivityLog
import utils.clock as clock


async def handle_get_open_positions(session: Optional[AsyncSession] = None, settings: Optional[dict] = None, **kwargs) -> Any:
    handlers = PositionToolHandlers(settings)
    return await handlers.get_open_positions(session=session)


async def handle_get_account_info(session: Optional[AsyncSession] = None, settings: Optional[dict] = None, **kwargs) -> Optional[Dict[str, Any]]:
    handlers = PositionToolHandlers(settings)
    return await handlers.get_account_info(session=session)


async def handle_propose_action(inp: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    if session:
        session.add(ActivityLog(
            category="telegram",
            description=f"Action proposed: {inp.get('action_type')} — {inp.get('reason', '')}",
            actor="ai_agent",
            timestamp=clock.now(),
        ))
        await session.commit()
    return {
        "status": "proposed",
        "message": "Action logged. Telegram confirmation will be sent by the bot layer.",
        "action_type": inp.get("action_type"),
        "params": inp.get("params"),
    }


async def handle_calculate_position_size(args: dict, session: Optional[AsyncSession] = None, settings: Optional[dict] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    handlers = ExecutionToolHandlers(settings or getattr(executor, "settings", {}))
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    symbol = sym or args.get("symbol") or getattr(executor, "symbol", "EURUSD")
    entry_price = float(args.get("entry_price", 0.0))
    stop_loss = float(args.get("stop_loss", 0.0))
    risk_pct = float(args.get("risk_percent") or args.get("risk_pct") or 1.0)
    effective_session = session or getattr(executor, "session", None)
    return await handlers.calculate_position_size(
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        risk_pct=risk_pct,
        session=effective_session,
        **args
    )


@register_tool("get_open_positions", aliases=["get_open_position", "get_positions"], category="POSITION", parallel_safe=True)
class GetOpenPositionsHandler(ToolHandler):
    name = "get_open_positions"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        settings = getattr(executor, "settings", {}) or {}
        return await handle_get_open_positions(session=session, settings=settings, **kwargs)


@register_tool("get_account_info", aliases=["account_info", "account_balance"], category="POSITION", parallel_safe=True)
class GetAccountInfoHandler(ToolHandler):
    name = "get_account_info"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        settings = getattr(executor, "settings", {}) or {}
        return await handle_get_account_info(session=session, settings=settings, **kwargs)


@register_tool("propose_action", aliases=["submit_action_proposal"], category="EXECUTION", parallel_safe=False)
class ProposeActionHandler(ToolHandler):
    name = "propose_action"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_propose_action(args, session=session, **kwargs)


@register_tool("calculate_position_size", aliases=["calculate_size", "position_size"], category="EXECUTION", parallel_safe=True)
class CalculatePositionSizeHandler(ToolHandler):
    name = "calculate_position_size"
    category = "EXECUTION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_calculate_position_size(args, session=session, executor=executor, **kwargs)
