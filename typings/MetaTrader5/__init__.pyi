"""Type stubs for MetaTrader5 package."""

from typing import Any, Optional, Tuple, Union
import numpy as np

# Timeframes
TIMEFRAME_M1: int
TIMEFRAME_M2: int
TIMEFRAME_M3: int
TIMEFRAME_M4: int
TIMEFRAME_M5: int
TIMEFRAME_M6: int
TIMEFRAME_M10: int
TIMEFRAME_M12: int
TIMEFRAME_M15: int
TIMEFRAME_M20: int
TIMEFRAME_M30: int
TIMEFRAME_H1: int
TIMEFRAME_H2: int
TIMEFRAME_H3: int
TIMEFRAME_H4: int
TIMEFRAME_H6: int
TIMEFRAME_H8: int
TIMEFRAME_H12: int
TIMEFRAME_D1: int
TIMEFRAME_W1: int
TIMEFRAME_MN1: int

# Order types
ORDER_TYPE_BUY: int
ORDER_TYPE_SELL: int
ORDER_TYPE_BUY_LIMIT: int
ORDER_TYPE_SELL_LIMIT: int
ORDER_TYPE_BUY_STOP: int
ORDER_TYPE_SELL_STOP: int
ORDER_TYPE_BUY_STOP_LIMIT: int
ORDER_TYPE_SELL_STOP_LIMIT: int
ORDER_TYPE_CLOSE_BY: int

# Trade actions
TRADE_ACTION_DEAL: int
TRADE_ACTION_PENDING: int
TRADE_ACTION_SLTP: int
TRADE_ACTION_MODIFY: int
TRADE_ACTION_REMOVE: int
TRADE_ACTION_CLOSE_BY: int

# Order filling
ORDER_FILLING_FOK: int
ORDER_FILLING_IOC: int
ORDER_FILLING_RETURN: int
ORDER_FILLING_BOC: int

# Order time
ORDER_TIME_GTC: int
ORDER_TIME_DAY: int
ORDER_TIME_SPECIFIED: int
ORDER_TIME_SPECIFIED_DAY: int

# Trade return codes
TRADE_RETCODE_REQUOTE: int
TRADE_RETCODE_REJECT: int
TRADE_RETCODE_CANCEL: int
TRADE_RETCODE_PLACED: int
TRADE_RETCODE_DONE: int
TRADE_RETCODE_DONE_PARTIAL: int
TRADE_RETCODE_ERROR: int
TRADE_RETCODE_TIMEOUT: int
TRADE_RETCODE_INVALID: int
TRADE_RETCODE_INVALID_VOLUME: int
TRADE_RETCODE_INVALID_PRICE: int
TRADE_RETCODE_INVALID_STOPS: int
TRADE_RETCODE_TRADE_DISABLED: int
TRADE_RETCODE_MARKET_CLOSED: int
TRADE_RETCODE_NO_MONEY: int
TRADE_RETCODE_PRICE_CHANGED: int
TRADE_RETCODE_PRICE_OFF: int
TRADE_RETCODE_INVALID_EXPIRATION: int
TRADE_RETCODE_ORDER_CHANGED: int
TRADE_RETCODE_TOO_MANY_REQUESTS: int
TRADE_RETCODE_NO_CHANGES: int
TRADE_RETCODE_SERVER_DISABLES_AT: int
TRADE_RETCODE_CLIENT_DISABLES_AT: int
TRADE_RETCODE_LOCKED: int
TRADE_RETCODE_FROZEN: int
TRADE_RETCODE_INVALID_FILL: int
TRADE_RETCODE_CONNECTION: int
TRADE_RETCODE_ONLY_REAL: int
TRADE_RETCODE_LIMIT_ORDERS: int
TRADE_RETCODE_LIMIT_VOLUME: int
TRADE_RETCODE_INVALID_ORDER: int
TRADE_RETCODE_POSITION_CLOSED: int

# Ticks flags
COPY_TICKS_ALL: int
COPY_TICKS_INFO: int
COPY_TICKS_TRADE: int

# Book types
BOOK_TYPE_SELL: int
BOOK_TYPE_BUY: int
BOOK_TYPE_SELL_MARKET: int
BOOK_TYPE_BUY_MARKET: int

# Deal reasons
DEAL_REASON_CLIENT: int
DEAL_REASON_MOBILE: int
DEAL_REASON_WEB: int
DEAL_REASON_EXPERT: int
DEAL_REASON_SL: int
DEAL_REASON_TP: int
DEAL_REASON_SO: int
DEAL_REASON_ROLLOVER: int
DEAL_REASON_VMARGIN: int
DEAL_REASON_SPLIT: int

# Deal types
DEAL_TYPE_BUY: int
DEAL_TYPE_SELL: int
DEAL_TYPE_BALANCE: int
DEAL_TYPE_CREDIT: int
DEAL_TYPE_CHARGE: int
DEAL_TYPE_CORRECTION: int
DEAL_TYPE_BONUS: int
DEAL_TYPE_COMMISSION: int
DEAL_TYPE_COMMISSION_DAILY: int
DEAL_TYPE_COMMISSION_MONTHLY: int
DEAL_TYPE_COMMISSION_AGENT_DAILY: int
DEAL_TYPE_COMMISSION_AGENT_MONTHLY: int
DEAL_TYPE_INTEREST: int
DEAL_TYPE_BUY_CANCELED: int
DEAL_TYPE_SELL_CANCELED: int
DEAL_DIVIDEND: int
DEAL_DIVIDEND_FRANKED: int
DEAL_TAX: int

# Order states
ORDER_STATE_STARTED: int
ORDER_STATE_PLACED: int
ORDER_STATE_CANCELED: int
ORDER_STATE_PARTIAL: int
ORDER_STATE_FILLED: int
ORDER_STATE_REJECTED: int
ORDER_STATE_EXPIRED: int
ORDER_STATE_REQUEST_ADD: int
ORDER_STATE_REQUEST_MODIFY: int
ORDER_STATE_REQUEST_CANCEL: int

# Functions
def initialize(
    path: Optional[str] = ...,
    login: Optional[int] = ...,
    password: Optional[str] = ...,
    server: Optional[str] = ...,
    timeout: Optional[int] = ...,
    portable: Optional[bool] = ...,
) -> bool: ...
def shutdown() -> None: ...
def version() -> Tuple[int, int, str]: ...
def last_error() -> Tuple[int, str]: ...
def terminal_info() -> Any: ...
def account_info() -> Any: ...
def symbols_total() -> int: ...
def symbols_get(group: str = ...) -> Tuple[Any, ...]: ...
def symbol_info(symbol: str) -> Any: ...
def symbol_info_tick(symbol: str) -> Any: ...
def symbol_select(symbol: str, enable: bool = ...) -> bool: ...
def market_book_add(symbol: str) -> bool: ...
def market_book_get(symbol: str) -> Optional[Tuple[Any, ...]]: ...
def market_book_release(symbol: str) -> bool: ...
def copy_rates_from(symbol: str, timeframe: int, date_from: Any, count: int) -> Optional[np.ndarray]: ...
def copy_rates_from_pos(symbol: str, timeframe: int, start_pos: int, count: int) -> Optional[np.ndarray]: ...
def copy_rates_range(symbol: str, timeframe: int, date_from: Any, date_to: Any) -> Optional[np.ndarray]: ...
def copy_ticks_from(symbol: str, date_from: Any, count: int, flags: int) -> Optional[np.ndarray]: ...
def copy_ticks_range(symbol: str, date_from: Any, date_to: Any, flags: int) -> Optional[np.ndarray]: ...
def orders_total() -> int: ...
def orders_get(symbol: str = ..., group: str = ..., ticket: int = ...) -> Optional[Tuple[Any, ...]]: ...
def order_calc_margin(action: int, symbol: str, volume: float, price: float) -> Optional[float]: ...
def order_calc_profit(
    action: int, symbol: str, volume: float, price_open: float, price_close: float
) -> Optional[float]: ...
def order_check(request: dict) -> Any: ...
def order_send(request: dict) -> Any: ...
def positions_total() -> int: ...
def positions_get(symbol: str = ..., group: str = ..., ticket: int = ...) -> Optional[Tuple[Any, ...]]: ...
def history_orders_total(date_from: Any, date_to: Any) -> int: ...
def history_orders_get(
    date_from: Any = ..., date_to: Any = ..., group: str = ..., ticket: int = ..., position: int = ...
) -> Optional[Tuple[Any, ...]]: ...
def history_deals_total(date_from: Any, date_to: Any) -> int: ...
def history_deals_get(
    date_from: Any = ..., date_to: Any = ..., group: str = ..., ticket: int = ..., position: int = ...
) -> Optional[Tuple[Any, ...]]: ...
