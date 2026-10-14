"""
Synchronous MT5 order and position manipulation primitives.
"""

import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .constants import _resolve_broker_symbol, logger
from .primitives import _calculate_dom_vwap, format_mt5_error


def _place_order(
    symbol: str,
    direction: str,
    volume: float,
    price: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    comment: str,
    order_type: str,
    max_spread_multiplier: Optional[float] = None,
) -> dict[str, Any]:
    """
    Execute a trade request on MT5.
    Handles MARKET (instant) and LIMIT/STOP (pending) order types.
    """
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    resolved_symbol = _resolve_broker_symbol(symbol)
    info = mt5.symbol_info(resolved_symbol)
    if info is None:
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": f"Symbol {resolved_symbol} (original: {symbol}) not found on broker terminal",
            "retcode": -1,
        }

    # Strict volume floor quantization to prevent broker volume rejection
    raw_step = getattr(info, "volume_step", 0.01)
    step = float(raw_step) if isinstance(raw_step, (int, float)) and raw_step > 0 else 0.01
    raw_min = getattr(info, "volume_min", 0.01)
    min_vol = float(raw_min) if isinstance(raw_min, (int, float)) and raw_min > 0 else 0.01
    raw_max = getattr(info, "volume_max", 100.0)
    max_vol = float(raw_max) if isinstance(raw_max, (int, float)) and raw_max > 0 else 100.0
    steps = math.floor((float(volume) / step) + 1e-9)
    if steps <= 0:
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": f"Volume {volume} below minimum step {step} for {resolved_symbol}",
            "retcode": -1,
        }
    quantized_vol = max(min_vol, min(max_vol, steps * step))
    vol_decimals = 2 if step >= 0.01 else (3 if step >= 0.001 else 0)
    final_volume = round(quantized_vol, vol_decimals)

    # Normalize SL/TP to tick size to prevent 'Invalid Stops' rejection
    def _normalize(val: float) -> float:
        if not info.trade_tick_size:
            return round(val, info.digits)
        return round(round(val / info.trade_tick_size) * info.trade_tick_size, info.digits)

    # 1. Market Spread Safety Check
    tick = mt5.symbol_info_tick(resolved_symbol)
    if tick is None:
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": f"Cannot get tick for spread check on {resolved_symbol}",
            "retcode": -1,
        }

    # Level 2 DOM Ladder Walk Check for large lot orders (Subsystem 5)
    if float(final_volume) >= 1.0:
        try:
            dom_res = _calculate_dom_vwap(resolved_symbol, direction, float(final_volume))
            if dom_res.get("has_dom") and dom_res.get("slippage_pts", 0.0) > 40.0:
                logger.warning(
                    f"[{resolved_symbol}] Level 2 DOM Ladder Walk: large lot {final_volume} expected slippage "
                    f"{dom_res['slippage_pts']:.1f} pts exceeds 40.0 pts tolerance. "
                    f"VWAP={dom_res['vwap']} vs BBO={dom_res['bbo_price']}."
                )
        except Exception as dom_err:
            logger.debug(f"[{resolved_symbol}] DOM VWAP check non-fatal: {dom_err}")

    # 2. Normalize Direction & Map Action/Order Type
    direction = (direction or "").lower().strip()
    if direction not in ("buy", "sell"):
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": f"Invalid direction {direction} for {symbol}",
            "retcode": -1,
        }

    order_type_upper = (order_type or "market").upper()
    if order_type_upper in ("BUY_LIMIT", "LIMIT") and direction == "buy":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_BUY_LIMIT
        order_price = price
    elif order_type_upper in ("SELL_LIMIT", "LIMIT") and direction == "sell":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_SELL_LIMIT
        order_price = price
    elif order_type_upper in ("BUY_STOP", "STOP") and direction == "buy":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_BUY_STOP
        order_price = price
    elif order_type_upper in ("SELL_STOP", "STOP") and direction == "sell":
        action = mt5.TRADE_ACTION_PENDING
        mt5_order_type = mt5.ORDER_TYPE_SELL_STOP
        order_price = price
    elif direction == "buy":
        action = mt5.TRADE_ACTION_DEAL
        mt5_order_type = mt5.ORDER_TYPE_BUY
        order_price = tick.ask
    elif direction == "sell":
        action = mt5.TRADE_ACTION_DEAL
        mt5_order_type = mt5.ORDER_TYPE_SELL
        order_price = tick.bid
    else:
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": f"Unsupported order direction {direction}",
            "retcode": -1,
        }

    if not order_price or order_price <= 0:
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": f"Invalid calculated price {order_price} for {symbol}",
            "retcode": -1,
        }

    # Query supported fill mode from symbol info
    filling_mode = info.filling_mode
    if filling_mode & 1:  # ORDER_FILLING_FOK
        fill_type = mt5.ORDER_FILLING_FOK
    elif filling_mode & 2:  # ORDER_FILLING_IOC
        fill_type = mt5.ORDER_FILLING_IOC
    else:
        fill_type = mt5.ORDER_FILLING_RETURN

    request = {
        "action": action,
        "symbol": resolved_symbol,
        "volume": float(final_volume),
        "type": mt5_order_type,
        "price": float(order_price),
        "sl": _normalize(sl) if sl else 0.0,
        "tp": _normalize(tp) if tp else 0.0,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": fill_type,
        "magic": 20250101,  # EA magic number to identify AI-placed orders
        "deviation": 20,  # Max price deviation in points for market orders
    }

    # Pre-flight order_check validation
    try:
        check_result = mt5.order_check(request)
        if check_result is not None:
            check_retcode = getattr(check_result, "retcode", 0)
            if isinstance(check_retcode, int) and check_retcode not in (0, 10008, 10009):
                err_msg = f"Pre-flight order_check rejected: {format_mt5_error(check_retcode, getattr(check_result, 'comment', ''))}"
                logger.warning(f"[{resolved_symbol}] {err_msg}")
                return {
                    "success": False,
                    "ticket": None,
                    "price": None,
                    "error": err_msg,
                    "retcode": check_retcode,
                }
    except Exception as chk_ex:
        logger.debug(f"[{resolved_symbol}] order_check non-fatal: {chk_ex}")

    max_retries = 2
    result = None
    for attempt in range(max_retries + 1):
        result = mt5.order_send(request)
        if result is None:
            return {
                "success": False,
                "ticket": None,
                "price": None,
                "error": f"order_send returned None: {mt5.last_error()}",
                "retcode": -1,
            }

        done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
        placed_code = getattr(mt5, "TRADE_RETCODE_PLACED", 10008)
        ret_val = getattr(result, "retcode", None)
        if ret_val in (done_code, placed_code, 10009, 10008):
            break

        # Transient requote / price drift handling
        req_code = getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004)
        inv_code = getattr(mt5, "TRADE_RETCODE_INVALID_PRICE", 10015)
        off_code = getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021)
        transient_codes = (req_code, inv_code, off_code, 10004, 10015, 10021)
        if getattr(result, "retcode", None) in transient_codes and attempt < max_retries:
            time.sleep(0.1)  # 100ms rapid pause
            deal_action = getattr(mt5, "TRADE_ACTION_DEAL", 1)
            if request.get("action") == deal_action or request.get("action") == 1:
                latest_tick = mt5.symbol_info_tick(resolved_symbol)
                if latest_tick:
                    new_price = (
                        getattr(latest_tick, "ask", None) if direction == "buy" else getattr(latest_tick, "bid", None)
                    )
                    if new_price and new_price > 0:
                        request["price"] = float(new_price)
            continue
        break

    if result is None:
        return {
            "success": False,
            "ticket": None,
            "price": None,
            "error": "order_send returned None",
            "retcode": -1,
        }

    done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    placed_code = getattr(mt5, "TRADE_RETCODE_PLACED", 10008)
    res_retcode = getattr(result, "retcode", -1)
    success = res_retcode in (done_code, placed_code, 10009, 10008)
    ticket_id = getattr(result, "order", None)
    if success and not ticket_id:
        ticket_id = getattr(result, "deal", None)
    return {
        "success": success,
        "ticket": ticket_id if success else None,
        "price": getattr(result, "price", None) if success else None,
        "error": None if success else format_mt5_error(res_retcode, getattr(result, "comment", "")),
        "retcode": res_retcode,
        "volume": getattr(result, "volume", None) if success else None,
    }


def _modify_position(ticket: Any, sl: Optional[float], tp: Optional[float]) -> dict[str, Any]:
    """Modify SL/TP on an existing open position."""
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    try:
        ticket_id = int(str(ticket).strip())
    except ValueError, TypeError:
        logger.warning(f"Failed to parse ticket: {ticket!r}")
        return {"success": False, "error": f"Invalid ticket: {ticket}", "retcode": -1}

    # Get current position to preserve existing SL/TP if not being changed
    pos = mt5.positions_get(ticket=ticket_id)
    if not pos:
        return {"success": False, "error": f"Position {ticket_id} not found", "retcode": -1}

    current = pos[0]
    info = mt5.symbol_info(current.symbol)

    def _normalize(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        if info is None or not getattr(info, "trade_tick_size", None):
            digits = getattr(info, "digits", 5) if info else 5
            return round(float(val), digits)
        return round(round(float(val) / info.trade_tick_size) * info.trade_tick_size, info.digits)

    normalized_sl = _normalize(sl) if sl is not None else current.sl
    normalized_tp = _normalize(tp) if tp is not None else current.tp

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": current.symbol,
        "position": ticket_id,
        "sl": float(normalized_sl) if normalized_sl is not None else 0.0,
        "tp": float(normalized_tp) if normalized_tp is not None else 0.0,
        "magic": 20250101,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": str(mt5.last_error()), "retcode": -1}

    success = getattr(result, "retcode", -1) == getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    res_retcode = getattr(result, "retcode", -1)
    return {
        "success": success,
        "error": None if success else format_mt5_error(res_retcode, getattr(result, "comment", "")),
        "retcode": res_retcode,
    }


def _close_position(
    ticket: Any,
    volume: Optional[float],
    comment: str,
    lots: Optional[float] = None,
) -> dict[str, Any]:
    """Close an open position (fully or partially)."""
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    if volume is None and lots is not None:
        volume = lots

    try:
        ticket_id = int(str(ticket).strip())
    except ValueError, TypeError:
        logger.warning(f"Failed to parse ticket: {ticket!r}")
        return {"success": False, "price": None, "profit": None, "error": f"Invalid ticket: {ticket}", "retcode": -1}

    # Fetch current position details
    pos = mt5.positions_get(ticket=ticket_id)
    if not pos:
        return {
            "success": False,
            "price": None,
            "profit": None,
            "error": f"Position {ticket_id} not found",
            "retcode": -1,
        }

    current = pos[0]
    close_volume = volume if volume is not None else current.volume

    # Close requires the opposite direction
    tick = mt5.symbol_info_tick(current.symbol)
    if tick is None:
        # Fallback to symbol_info if tick fails
        info = mt5.symbol_info(current.symbol)
        if info is None:
            return {
                "success": False,
                "price": None,
                "profit": None,
                "error": f"Failed to get current price for {current.symbol}. Market closed?",
                "retcode": -1,
            }
        bid_price = info.bid
        ask_price = info.ask
    else:
        bid_price = tick.bid
        ask_price = tick.ask

    if current.type == getattr(mt5, "POSITION_TYPE_BUY", 0):
        close_type = getattr(mt5, "ORDER_TYPE_SELL", 1)
        close_price = bid_price
    else:
        close_type = getattr(mt5, "ORDER_TYPE_BUY", 0)
        close_price = ask_price

    # Query supported fill mode from symbol info
    info = mt5.symbol_info(current.symbol)
    filling_mode = info.filling_mode if info else 0
    if filling_mode & 1:  # ORDER_FILLING_FOK
        fill_type = getattr(mt5, "ORDER_FILLING_FOK", 0)
    elif filling_mode & 2:  # ORDER_FILLING_IOC
        fill_type = getattr(mt5, "ORDER_FILLING_IOC", 1)
    else:
        fill_type = getattr(mt5, "ORDER_FILLING_RETURN", 2)

    request = {
        "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
        "symbol": current.symbol,
        "volume": float(close_volume),
        "type": close_type,
        "position": ticket_id,
        "price": float(close_price),
        "comment": comment[:31],
        "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
        "type_filling": fill_type,
        "deviation": 20,
        "magic": 20250101,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "price": None, "profit": None, "error": str(mt5.last_error()), "retcode": -1}

    res_retcode = getattr(result, "retcode", -1)
    max_retries = 2
    for retry_idx in range(max_retries):
        if res_retcode in (10004, 10015, 10021):
            logger.warning(
                f"_close_position received requote/price-change retcode {res_retcode} for ticket {ticket_id}. "
                f"Retrying ({retry_idx + 1}/{max_retries}) with updated tick price..."
            )
            time.sleep(0.1)
            t_retry = mt5.symbol_info_tick(current.symbol)
            if t_retry:
                new_price = t_retry.bid if close_type == getattr(mt5, "ORDER_TYPE_SELL", 1) else t_retry.ask
                request["price"] = float(new_price)
            result = mt5.order_send(request)
            if result is None:
                break
            res_retcode = getattr(result, "retcode", -1)
        else:
            break

    success = res_retcode == getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    return {
        "success": success,
        "price": getattr(result, "price", None) if (result and success) else None,
        "profit": getattr(current, "profit", None) if success else None,
        "error": None
        if success
        else format_mt5_error(res_retcode, getattr(result, "comment", "") if result else "order_send failed"),
        "retcode": res_retcode,
    }


def _get_open_positions(symbol: Optional[str] = None) -> list[dict[str, Any]]:
    """Fetch all open positions from MT5."""
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    if symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if positions is None:
        return []

    result = []
    for p in positions:
        result.append(
            {
                "ticket": p.ticket,
                "identifier": getattr(p, "identifier", p.ticket),
                "symbol": p.symbol,
                "type": p.type,  # 0=BUY, 1=SELL
                "direction": "buy" if p.type == 0 else "sell",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "comment": p.comment,
                "magic": p.magic,
                "time": datetime.fromtimestamp(p.time, tz=timezone.utc),
            }
        )
    return result


def _get_orders(symbol: Optional[str] = None) -> list[dict[str, Any]]:
    """Fetch all active pending orders from MT5."""
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    if symbol:
        orders = mt5.orders_get(symbol=symbol)
    else:
        orders = mt5.orders_get()

    if orders is None:
        return []

    result = []
    for o in orders:
        order_type_val = getattr(o, "type", 0)
        # MT5 pending types: 2=BUY_LIMIT, 3=SELL_LIMIT, 4=BUY_STOP, 5=SELL_STOP, 6=BUY_STOP_LIMIT, 7=SELL_STOP_LIMIT
        direction = "buy" if order_type_val in (2, 4, 6) else "sell"
        result.append(
            {
                "ticket": getattr(o, "ticket", None),
                "symbol": getattr(o, "symbol", ""),
                "type": order_type_val,
                "direction": direction,
                "volume": getattr(o, "volume_current", getattr(o, "volume_initial", 0.0)),
                "volume_initial": getattr(o, "volume_initial", 0.0),
                "volume_current": getattr(o, "volume_current", 0.0),
                "price_open": getattr(o, "price_open", 0.0),
                "price_current": getattr(o, "price_current", 0.0),
                "sl": getattr(o, "sl", None),
                "tp": getattr(o, "tp", None),
                "comment": getattr(o, "comment", ""),
                "magic": getattr(o, "magic", 0),
                "time": datetime.fromtimestamp(getattr(o, "time_setup", 0), tz=timezone.utc)
                if getattr(o, "time_setup", 0)
                else None,
                "state": getattr(o, "state", None),
            }
        )
    return result


def _cancel_order(ticket: Any) -> dict[str, Any]:
    """Cancel pending order by ticket in MT5."""
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    try:
        ticket_id = int(str(ticket).strip())
    except ValueError, TypeError:
        logger.warning(f"Failed to parse ticket: {ticket!r}")
        ticket_id = 0

    request = {
        "action": getattr(mt5, "TRADE_ACTION_REMOVE", 8),
        "order": ticket_id,
    }
    result = mt5.order_send(request)
    if result is None:
        return {
            "success": False,
            "error": f"order_send returned None: {mt5.last_error()}",
            "retcode": -1,
        }
    done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
    res_retcode = getattr(result, "retcode", -1)
    success = res_retcode == done_code or res_retcode == 10009
    return {
        "success": success,
        "ticket": ticket_id,
        "retcode": res_retcode,
        "error": None if success else format_mt5_error(res_retcode, getattr(result, "comment", "")),
    }


def _get_deal_history(ticket: Any) -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    try:
        ticket_id = int(str(ticket).strip())
    except ValueError, TypeError:
        logger.warning(f"Failed to parse ticket: {ticket!r}")
        ticket_id = 0
    deals = mt5.history_deals_get(position=ticket_id)
    return deals if deals else []


def _get_order_history(ticket: Any) -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    try:
        ticket_id = int(str(ticket).strip())
    except ValueError, TypeError:
        logger.warning(f"Failed to parse ticket: {ticket!r}")
        ticket_id = 0
    orders = mt5.history_orders_get(ticket=ticket_id)
    return orders if orders else []
