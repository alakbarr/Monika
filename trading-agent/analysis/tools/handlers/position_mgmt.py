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


async def handle_get_pending_orders(args: Optional[dict] = None, session: Optional[AsyncSession] = None, settings: Optional[dict] = None, **kwargs) -> Any:
    handlers = PositionToolHandlers(settings)
    sym = args.get("symbol") if args else None
    return await handlers.get_pending_orders(symbol=sym, session=session)


async def handle_get_account_info(session: Optional[AsyncSession] = None, settings: Optional[dict] = None, **kwargs) -> Optional[Dict[str, Any]]:
    handlers = PositionToolHandlers(settings)
    return await handlers.get_account_info(session=session)


async def handle_get_risk_state(session: Optional[AsyncSession] = None, settings: Optional[dict] = None, **kwargs) -> Dict[str, Any]:
    handlers = PositionToolHandlers(settings)
    return await handlers.get_risk_state(session=session)


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
    clean_sym = symbol.strip().upper().replace('/', '')
    
    entry_price = float(args.get("entry_price") or 0.0)
    stop_loss = float(args.get("stop_loss") or 0.0)
    risk_pct = float(args.get("risk_percent") or args.get("risk_pct") or 1.0)
    effective_session = session or getattr(executor, "session", None)

    # Fallback to current market price if entry price is not provided
    if entry_price <= 0:
        try:
            from execution.mt5_client import get_mt5_client
            client = get_mt5_client(settings or getattr(executor, "settings", {}))
            if client:
                tick = await client.get_current_price(clean_sym)
                if tick and tick.get("bid"):
                    entry_price = float(tick["bid"])
        except Exception:
            pass

    # If stop loss is not provided, estimate based on 30 pips default
    if stop_loss <= 0 and entry_price > 0:
        from risk.position_sizing import DEFAULT_INSTRUMENTS
        spec = DEFAULT_INSTRUMENTS.get(clean_sym)
        pip_size = spec.pip_size if spec else (0.01 if "JPY" in clean_sym or "XAU" in clean_sym else 0.0001)
        direction = (args.get("direction") or "buy").lower()
        if direction == "sell":
            stop_loss = entry_price + (30 * pip_size)
        else:
            stop_loss = entry_price - (30 * pip_size)

    return await handlers.calculate_position_size(
        symbol=clean_sym,
        entry_price=entry_price,
        stop_loss=stop_loss,
        risk_pct=risk_pct,
        session=effective_session,
        **args
    )


async def handle_calculate_margin(args: dict, session: Optional[AsyncSession] = None, settings: Optional[dict] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    handlers = ExecutionToolHandlers(settings or getattr(executor, "settings", {}))
    sym = None
    if executor and hasattr(executor, "_resolve_symbol"):
        sym = executor._resolve_symbol(args)
    symbol = sym or args.get("symbol") or getattr(executor, "symbol", "EURUSD")
    lot_size = float(args.get("lot_size") or args.get("lots") or args.get("volume") or 1.0)
    action = args.get("action", "buy")
    price = float(args.get("price")) if args.get("price") is not None else None
    return await handlers.calculate_margin(symbol=symbol, lot_size=lot_size, action=action, price=price)


@register_tool("get_open_positions", aliases=["get_open_position", "get_positions"], category="POSITION", parallel_safe=True)
class GetOpenPositionsHandler(ToolHandler):
    name = "get_open_positions"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        settings = getattr(executor, "settings", {}) or {}
        return await handle_get_open_positions(session=session, settings=settings, **kwargs)


@register_tool("get_pending_orders", aliases=["get_pending_order", "get_orders", "pending_orders"], category="POSITION", parallel_safe=True)
class GetPendingOrdersHandler(ToolHandler):
    name = "get_pending_orders"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        settings = getattr(executor, "settings", {}) or {}
        return await handle_get_pending_orders(args=args, session=session, settings=settings, **kwargs)


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


@register_tool("calculate_margin", aliases=["calc_margin", "margin_calculator"], category="EXECUTION", parallel_safe=True)
class CalculateMarginHandler(ToolHandler):
    name = "calculate_margin"
    category = "EXECUTION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_calculate_margin(args, session=session, executor=executor, **kwargs)


@register_tool("get_risk_state", aliases=["risk_state", "current_risk_state"], category="POSITION", parallel_safe=True)
class GetRiskStateHandler(ToolHandler):
    name = "get_risk_state"
    category = "POSITION"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        settings = getattr(executor, "settings", {}) or {}
        return await handle_get_risk_state(session=session, settings=settings, **kwargs)


async def handle_set_trailing_stop(args: dict, session: Optional[AsyncSession] = None, settings: Optional[dict] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"success": False, "error": "No database session available"}
    
    ticket = args.get("ticket")
    symbol = args.get("symbol")
    trailing_pips = args.get("trailing_pips") or args.get("pips")
    trail_atr_multiple = args.get("trail_atr_multiple")
    breakeven_pips = args.get("breakeven_pips")
    only_profit = args.get("only_profit", False)
    
    override_data = {}
    if trailing_pips is not None:
        override_data["trailing_pips"] = float(trailing_pips)
    if breakeven_pips is not None:
        override_data["breakeven_pips"] = float(breakeven_pips)
    if trail_atr_multiple is not None:
        override_data["trail_atr_multiple"] = float(trail_atr_multiple)
    if args.get("disabled"):
        override_data["disabled"] = True

    stmt = select(Position).where(Position.status == "open")
    if ticket:
        stmt = stmt.where(Position.mt5_ticket == int(ticket))
    if symbol:
        stmt = stmt.where(Position.symbol == symbol.strip().upper().replace("/", ""))

    positions = list((await effective_session.execute(stmt)).scalars().all())
    if not positions:
        return {"success": True, "updated_count": 0, "message": "No matching open positions found."}

    import json
    updated = []
    for pos in positions:
        if only_profit and pos.pnl is not None and pos.pnl <= 0:
            continue
        pos.trailing_override_json = json.dumps(override_data)
        updated.append(pos.mt5_ticket)
    
    await effective_session.commit()
    return {
        "success": True,
        "updated_count": len(updated),
        "updated_tickets": updated,
        "override_config": override_data,
        "message": f"Updated trailing stop configuration for {len(updated)} position(s)."
    }


@register_tool("set_trailing_stop", aliases=["configure_trailing_stop", "update_trailing_stop"], category="POSITION", parallel_safe=False)
class SetTrailingStopHandler(ToolHandler):
    name = "set_trailing_stop"
    category = "POSITION"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        settings = getattr(executor, "settings", {}) or {}
        return await handle_set_trailing_stop(args, session=session, settings=settings, executor=executor, **kwargs)

