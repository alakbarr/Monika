# ==============================================================================
# File: analysis/tools/handlers/market_data/__init__.py
# ==============================================================================

"""
Market data tool handlers subpackage.
Provides quotes, price history, technical indicators, market structures,
SMC zones, charts, and instrument specifications.
"""

from monika.application.analysis.tools.handlers.market_data_handlers.base import (
    _get_session_and_symbol,
    logger,
)
from monika.application.analysis.tools.handlers.market_data_handlers.charts import (
    handle_get_chart,
    handle_plot_equity_curve,
    handle_plot_price_chart,
)
from monika.application.analysis.tools.handlers.market_data_handlers.quotes_prices import (
    handle_export_historical_data_csv,
    handle_get_market_quote,
    handle_get_price_history,
    handle_get_spread_snapshot,
    handle_get_symbol_specification,
    handle_get_synthetic_cross_rate,
)
from monika.application.analysis.tools.handlers.market_data_handlers.registration import (
    register_market_data_tools,
    register_market_data_tools_core,
)
from monika.application.analysis.tools.handlers.market_data_handlers.structures_smc import (
    handle_detect_candlestick_patterns,
    handle_get_fibonacci_levels,
    handle_get_optimal_intraday_levels,
    handle_get_smc_zones,
    handle_get_sr_zones,
    handle_get_structure_breaks,
    handle_get_swing_points,
    handle_scan_chart_patterns,
)
from monika.application.analysis.tools.handlers.market_data_handlers.technicals import (
    handle_get_atr,
    handle_get_daily_range_context,
    handle_get_divergences,
    handle_get_ichimoku,
    handle_get_multi_timeframe_summary,
    handle_get_pivot_points,
    handle_get_price_momentum,
    handle_get_seasonality,
    handle_get_technical_indicators,
)

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
