# ==============================================================================
# File: analysis/tools/handlers/market_data_tools.py
# ==============================================================================

"""
Backward-compatible facade for market data tool handlers.
All implementations have been refactored into `monika.application.analysis.tools.handlers.market_data.*`.
"""

import sys
import types
from typing import Any

import monika.application.analysis.tools.handlers.market_data as _market_data_pkg
from monika.application.analysis.tools.handlers.market_data import (
    _get_session_and_symbol,
    base as _base_mod,
    charts as _charts_mod,
    handle_detect_candlestick_patterns,
    handle_export_historical_data_csv,
    handle_get_atr,
    handle_get_chart,
    handle_get_daily_range_context,
    handle_get_divergences,
    handle_get_fibonacci_levels,
    handle_get_ichimoku,
    handle_get_market_quote,
    handle_get_multi_timeframe_summary,
    handle_get_optimal_intraday_levels,
    handle_get_pivot_points,
    handle_get_price_history,
    handle_get_price_momentum,
    handle_get_seasonality,
    handle_get_smc_zones,
    handle_get_spread_snapshot,
    handle_get_sr_zones,
    handle_get_structure_breaks,
    handle_get_swing_points,
    handle_get_symbol_specification,
    handle_get_synthetic_cross_rate,
    handle_get_technical_indicators,
    handle_plot_equity_curve,
    handle_plot_price_chart,
    handle_scan_chart_patterns,
    logger,
    quotes_prices as _quotes_prices_mod,
    register_market_data_tools,
    register_market_data_tools_core,
    registration as _registration_mod,
    structures_smc as _structures_smc_mod,
    technicals as _technicals_mod,
)

# Preserve automatic module import registrations
register_market_data_tools_core()
register_market_data_tools()

__all__ = [
    "_get_session_and_symbol",
    "logger",
    "handle_get_price_history",
    "handle_get_technical_indicators",
    "handle_get_synthetic_cross_rate",
    "handle_get_atr",
    "handle_get_swing_points",
    "handle_get_structure_breaks",
    "handle_get_sr_zones",
    "handle_get_smc_zones",
    "handle_get_fibonacci_levels",
    "handle_get_optimal_intraday_levels",
    "handle_get_daily_range_context",
    "handle_export_historical_data_csv",
    "handle_get_price_momentum",
    "handle_get_multi_timeframe_summary",
    "handle_get_chart",
    "handle_get_spread_snapshot",
    "handle_get_market_quote",
    "handle_detect_candlestick_patterns",
    "handle_plot_price_chart",
    "handle_plot_equity_curve",
    "handle_get_symbol_specification",
    "handle_get_pivot_points",
    "handle_get_ichimoku",
    "handle_scan_chart_patterns",
    "handle_get_seasonality",
    "handle_get_divergences",
    "register_market_data_tools_core",
    "register_market_data_tools",
]


class _MarketDataToolsFacadeModule(types.ModuleType):
    """Module proxy forwarding attribute mutations to submodules for transparent monkeypatching."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for submodule in (
            _market_data_pkg,
            _base_mod,
            _quotes_prices_mod,
            _technicals_mod,
            _structures_smc_mod,
            _charts_mod,
            _registration_mod,
        ):
            if hasattr(submodule, name):
                setattr(submodule, name, value)


_current_mod = sys.modules[__name__]
_proxy_mod = _MarketDataToolsFacadeModule(__name__, __doc__)
_proxy_mod.__dict__.update(_current_mod.__dict__)
sys.modules[__name__] = _proxy_mod
