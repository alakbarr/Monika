"""
MT5 client facade module for backward compatibility.
Delegates to modular submodules under monika.infrastructure.brokers.mt5.*
"""

import sys
import types
from typing import Any

from monika.infrastructure.brokers.mt5 import (
    MT5_RETCODE_DESCRIPTIONS,
    MT5Client,
    MT5ConnectionMixin,
    MT5ExecutionMixin,
    MT5MarketDataMixin,
    MT5MixinBase,
    MT5ProfileMismatchError,
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_NORMAL,
    PRIORITY_STANDARD,
    TIMEFRAME_MAP,
    _BROKER_SYMBOL_CACHE,
    _build_timeframe_map,
    _calculate_dom_vwap,
    _cancel_order,
    _capture_chart_screenshot,
    _close_position,
    _connect,
    _copy_rates_from_pos,
    _copy_rates_range,
    _copy_ticks_range,
    _disconnect,
    _get_account_info,
    _get_deal_history,
    _get_last_tick,
    _get_open_positions,
    _get_order_history,
    _get_orders,
    _get_symbol_info,
    _is_connected,
    _market_book_add,
    _market_book_get,
    _market_book_release,
    _modify_position,
    _place_order,
    _resolve_broker_symbol,
    format_mt5_error,
    get_mt5_client,
    logger,
)
from monika.infrastructure.brokers.mt5 import (
    client as _client_mod,
    connection as _conn_mod,
    constants as _const_mod,
    execution as _exec_mod,
    market_data as _md_mod,
    order_ops as _order_ops_mod,
    primitives as _prim_mod,
)

_SUBMODULES = (
    _const_mod,
    _prim_mod,
    _order_ops_mod,
    _conn_mod,
    _md_mod,
    _exec_mod,
    _client_mod,
)


class _MT5ClientFacadeModule(types.ModuleType):
    """Facade module ensuring backward-compatible imports and synchronizing dynamic patches to submodules."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for mod in _SUBMODULES:
            if hasattr(mod, name):
                setattr(mod, name, value)


_current_mod = sys.modules[__name__]
_facade_mod = _MT5ClientFacadeModule(__name__, __doc__)
_facade_mod.__dict__.update(_current_mod.__dict__)
sys.modules[__name__] = _facade_mod

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
