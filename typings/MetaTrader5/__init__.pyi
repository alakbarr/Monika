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

# Data structures
class SymbolInfo:
    custom: bool
    chart_mode: int
    select: bool
    visible: bool
    session_deals: int
    session_buy_orders: int
    session_sell_orders: int
    volume: float
    volumehigh: float
    volumelow: float
    time: int
    digits: int
    spread: int
    spread_float: bool
    ticks_bookdepth: int
    trade_calc_mode: int
    trade_mode: int
    start_time: int
    expiration_time: int
    trade_stops_level: int
    trade_freeze_level: int
    trade_exemode: int
    swap_mode: int
    swap_rollover3days: int
    margin_hedged_use_checking: bool
    expiration_mode: int
    filling_mode: int
    order_mode: int
    order_gtc_mode: int
    option_mode: int
    option_right: int
    bid: float
    bidhigh: float
    bidlow: float
    ask: float
    askhigh: float
    asklow: float
    last: float
    lasthigh: float
    lastlow: float
    volume_real: float
    volumehigh_real: float
    volumelow_real: float
    option_strike: float
    point: float
    trade_tick_value: float
    trade_tick_value_profit: float
    trade_tick_value_loss: float
    trade_tick_size: float
    trade_contract_size: float
    trade_accrued_interest: float
    trade_face_value: float
    trade_liquidity_rate: float
    volume_min: float
    volume_max: float
    volume_step: float
    volume_limit: float
    swap_long: float
    swap_short: float
    margin_initial: float
    margin_maintenance: float
    session_volume: float
    session_turnover: float
    session_interest: float
    session_buy_orders_volume: float
    session_sell_orders_volume: float
    session_open: float
    session_close: float
    session_aw: float
    session_tx: float
    session_pv: float
    session_re: float
    currency_base: str
    currency_profit: str
    currency_margin: str
    bank: str
    description: str
    exchange: str
    formula: str
    isin: str
    name: str
    page: str
    path: str
    def _asdict(self) -> dict[str, Any]: ...

class AccountInfo:
    login: int
    trade_mode: int
    leverage: int
    limit_orders: int
    margin_so_mode: int
    trade_allowed: bool
    trade_expert: bool
    margin_mode: int
    currency_digits: int
    fifo: bool
    balance: float
    credit: float
    profit: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    margin_so_call: float
    margin_so_so: float
    margin_initial: float
    margin_maintenance: float
    assets: float
    liabilities: float
    commission_blocked: float
    name: str
    server: str
    currency: str
    company: str
    def _asdict(self) -> dict[str, Any]: ...

class Tick:
    time: int
    bid: float
    ask: float
    last: float
    volume: float
    time_msc: int
    flags: int
    volume_real: float
    def _asdict(self) -> dict[str, Any]: ...

class OrderSendResult:
    retcode: int
    deal: int
    order: int
    volume: float
    price: float
    bid: float
    ask: float
    comment: str
    request_id: int
    retcode_external: int
    request: Any
    def _asdict(self) -> dict[str, Any]: ...

class TradePosition:
    ticket: int
    time: int
    time_msc: int
    time_update: int
    time_update_msc: int
    type: int
    magic: int
    identifier: int
    reason: int
    volume: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    swap: float
    profit: float
    symbol: str
    comment: str
    external_id: str
    def _asdict(self) -> dict[str, Any]: ...

class TradeOrder:
    ticket: int
    time_setup: int
    time_setup_msc: int
    time_done: int
    time_done_msc: int
    time_expiration: int
    type: int
    type_time: int
    type_filling: int
    state: int
    magic: int
    position_id: int
    position_by_id: int
    reason: int
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    price_stoplimit: float
    symbol: str
    comment: str
    external_id: str
    def _asdict(self) -> dict[str, Any]: ...

class TradeDeal:
    ticket: int
    order: int
    time: int
    time_msc: int
    type: int
    entry: int
    magic: int
    position_id: int
    reason: int
    volume: float
    price: float
    commission: float
    swap: float
    profit: float
    fee: float
    symbol: str
    comment: str
    external_id: str
    def _asdict(self) -> dict[str, Any]: ...

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
def account_info() -> Optional[AccountInfo]: ...
def symbols_total() -> int: ...
def symbols_get(group: str = ...) -> Tuple[SymbolInfo, ...]: ...
def symbol_info(symbol: str) -> Optional[SymbolInfo]: ...
def symbol_info_tick(symbol: str) -> Optional[Tick]: ...
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
def orders_get(symbol: str = ..., group: str = ..., ticket: int = ...) -> Optional[Tuple[TradeOrder, ...]]: ...
def order_calc_margin(action: int, symbol: str, volume: float, price: float) -> Optional[float]: ...
def order_calc_profit(
    action: int, symbol: str, volume: float, price_open: float, price_close: float
) -> Optional[float]: ...
def order_check(request: dict) -> OrderSendResult: ...
def order_send(request: dict) -> OrderSendResult: ...
def positions_total() -> int: ...
def positions_get(symbol: str = ..., group: str = ..., ticket: int = ...) -> Optional[Tuple[TradePosition, ...]]: ...
def history_orders_total(date_from: Any, date_to: Any) -> int: ...
def history_orders_get(
    date_from: Any = ..., date_to: Any = ..., group: str = ..., ticket: int = ..., position: int = ...
) -> Optional[Tuple[TradeOrder, ...]]: ...
def history_deals_total(date_from: Any, date_to: Any) -> int: ...
def history_deals_get(
    date_from: Any = ..., date_to: Any = ..., group: str = ..., ticket: int = ..., position: int = ...
) -> Optional[Tuple[TradeDeal, ...]]: ...
