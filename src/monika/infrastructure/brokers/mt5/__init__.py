"""
MT5 broker package: modular connection, market data, and execution submodules.
"""

from .base import MT5MixinBase
from .client import MT5Client, get_mt5_client
from .connection import MT5ConnectionMixin
from .constants import (
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_NORMAL,
    PRIORITY_STANDARD,
    TIMEFRAME_MAP,
    _BROKER_SYMBOL_CACHE,
    MT5ProfileMismatchError,
    _build_timeframe_map,
    _resolve_broker_symbol,
    logger,
)
from .execution import MT5ExecutionMixin
from .market_data import MT5MarketDataMixin
from .order_ops import (
    _cancel_order,
    _close_position,
    _get_deal_history,
    _get_open_positions,
    _get_order_history,
    _get_orders,
    _modify_position,
    _place_order,
)
from .primitives import (
    MT5_RETCODE_DESCRIPTIONS,
    _calculate_dom_vwap,
    _capture_chart_screenshot,
    _connect,
    _copy_rates_from_pos,
    _copy_rates_range,
    _copy_ticks_range,
    _disconnect,
    _get_account_info,
    _get_last_tick,
    _get_symbol_info,
    _is_connected,
    _market_book_add,
    _market_book_get,
    _market_book_release,
    format_mt5_error,
)

__all__ = [
    "MT5Client",
    "get_mt5_client",
    "MT5MixinBase",
    "MT5ConnectionMixin",
    "MT5MarketDataMixin",
    "MT5ExecutionMixin",
    "MT5ProfileMismatchError",
    "PRIORITY_CRITICAL",
    "PRIORITY_STANDARD",
    "PRIORITY_NORMAL",
    "PRIORITY_BACKGROUND",
    "TIMEFRAME_MAP",
    "_BROKER_SYMBOL_CACHE",
    "_resolve_broker_symbol",
    "_build_timeframe_map",
    "logger",
    "format_mt5_error",
    "MT5_RETCODE_DESCRIPTIONS",
    "_market_book_add",
    "_market_book_get",
    "_market_book_release",
    "_connect",
    "_disconnect",
    "_is_connected",
    "_get_account_info",
    "_get_symbol_info",
    "_copy_rates_from_pos",
    "_copy_rates_range",
    "_get_last_tick",
    "_copy_ticks_range",
    "_calculate_dom_vwap",
    "_capture_chart_screenshot",
    "_place_order",
    "_modify_position",
    "_close_position",
    "_get_open_positions",
    "_get_orders",
    "_cancel_order",
    "_get_deal_history",
    "_get_order_history",
]
