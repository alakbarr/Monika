# ==============================================================================
# File: analysis/tools/handlers/market_data/registration.py
# ==============================================================================

"""
Tool registration for market data tools into ToolRegistry.
"""

from typing import Optional

from monika.application.analysis.tools.handlers.market_data.charts import (
    handle_get_chart,
    handle_plot_equity_curve,
    handle_plot_price_chart,
)
from monika.application.analysis.tools.handlers.market_data.quotes_prices import (
    handle_export_historical_data_csv,
    handle_get_market_quote,
    handle_get_price_history,
    handle_get_spread_snapshot,
    handle_get_symbol_specification,
    handle_get_synthetic_cross_rate,
)
from monika.application.analysis.tools.handlers.market_data.structures_smc import (
    handle_detect_candlestick_patterns,
    handle_get_fibonacci_levels,
    handle_get_optimal_intraday_levels,
    handle_get_smc_zones,
    handle_get_sr_zones,
    handle_get_structure_breaks,
    handle_get_swing_points,
    handle_scan_chart_patterns,
)
from monika.application.analysis.tools.handlers.market_data.technicals import (
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
from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry


def register_market_data_tools_core(registry: Optional[ToolRegistry] = None):
    registry = registry or ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_symbol_specification",
            description="Get exact instrument specifications including contract size, pip size, pip value in USD, digits, and lot limits.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name or shorthand (e.g. XAUUSD, EURUSD, BTCUSD, US30)",
                    },
                },
                "required": ["symbol"],
            },
            handler=handle_get_symbol_specification,
            toolset="market_data",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_market_quote",
            description="Fetch current market quote (live tick or latest price) for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
            handler=handle_get_market_quote,
            toolset="market_data",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_multi_timeframe_summary",
            description="Composite multi-timeframe analysis across H1, H4, and D1.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_multi_timeframe_summary,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_chart",
            description="Generate candlestick chart image for visualization.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "candles": {"type": "integer"},
                },
            },
            handler=handle_get_chart,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="plot_price_chart",
            description="Plot and save a dark-theme candlestick chart with SMC overlays (Fair Value Gap boxes & Swing Pivots).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "candles": {"type": "integer"},
                    "overlay_smc": {"type": "boolean"},
                },
            },
            handler=handle_plot_price_chart,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="detect_candlestick_patterns",
            description="Detect classical candlestick patterns (Pin Bar/Hammer, Bullish/Bearish Engulfing, Doji, Morning/Evening Star).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "lookback": {"type": "integer"},
                },
            },
            handler=handle_detect_candlestick_patterns,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_spread_snapshot",
            description="Fetch current spread snapshot for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_spread_snapshot,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_synthetic_cross_rate",
            description="Computes synthetic cross-rates, spread, and estimated volatility for cross currency pairs.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
            handler=handle_get_synthetic_cross_rate,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_price_history",
            description="Fetch OHLCV candlestick price history for a symbol and timeframe.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
            handler=handle_get_price_history,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_technical_indicators",
            description="Fetch precalculated technical indicators (EMA, RSI, MACD, ATR, Bollinger, ADX).",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_technical_indicators,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_atr",
            description="Fetch the Average True Range (ATR) indicator value for volatility assessment.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_atr,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_swing_points",
            description="Fetch recent high and low swing points for market structure analysis.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_swing_points,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_structure_breaks",
            description="Fetch recent Break of Structure (BOS) and Change of Character (CHoCH) events.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_structure_breaks,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_smc_zones",
            description="Fetch institutional Smart Money Concepts zones (Order Blocks, FVG, S/R).",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_smc_zones,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_sr_zones",
            description="Fetch standalone Support/Resistance zones with strength ranking for a symbol and timeframe.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_sr_zones,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fibonacci_levels",
            description="Fetch Fibonacci retracement levels derived from recent swing points.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_fibonacci_levels,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_optimal_intraday_levels",
            description="Calculate optimal intraday entry, take-profit, and stop-loss levels.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "direction": {"type": "string"},
                    "entry_price": {"type": "number"},
                },
            },
            handler=handle_get_optimal_intraday_levels,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_daily_range_context",
            description="Fetch Average Daily Range (ADR) and current session range usage percentage.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "lookback_days": {"type": "integer"}},
            },
            handler=handle_get_daily_range_context,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_price_momentum",
            description="Fetch momentum indicators including RSI and MACD.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_price_momentum,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="export_historical_data_csv",
            description="Export historical OHLCV candle data to CSV format on disk.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "days_back": {"type": "integer"},
                    "output_filename": {"type": "string"},
                },
            },
            handler=handle_export_historical_data_csv,
            toolset="market_data",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


def register_market_data_tools(registry: Optional[ToolRegistry] = None):
    registry = registry or ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_price_history",
            description="Fetch historical OHLCV candle bars from MT5 or persistent storage.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
            handler=handle_get_price_history,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_technical_indicators",
            description="Fetch technical indicators (EMA, RSI, ATR, MACD, etc.) for a symbol and timeframe.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_technical_indicators,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_atr",
            description="Fetch Average True Range (ATR) volatility measure for a symbol.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "period": {"type": "integer"},
                },
            },
            handler=handle_get_atr,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_pivot_points",
            description="Calculate Classic, Camarilla, or Woodie Pivot Points (support and resistance levels) for a symbol.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "method": {"type": "string", "enum": ["classic", "camarilla", "woodie"]},
                    "timeframe": {"type": "string"},
                },
            },
            handler=handle_get_pivot_points,
            toolset="market_data",
        ),
        ToolDefinition(
            name="get_ichimoku",
            description="Calculate Ichimoku Kinko Hyo cloud indicators (Tenkan, Kijun, Senkou Span A/B, TK Cross).",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_ichimoku,
            toolset="market_data",
        ),
        ToolDefinition(
            name="scan_chart_patterns",
            description="Scan for classical chart patterns (Double Top/Bottom, H&S) and harmonic patterns (Gartley, Bat, Butterfly, Crab).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "order": {"type": "integer"},
                },
            },
            handler=handle_scan_chart_patterns,
            toolset="market_data",
        ),
        ToolDefinition(
            name="get_seasonality",
            description="Calculate historical monthly and day-of-week calendar seasonality tendencies for a symbol.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "type": {"type": "string", "enum": ["all", "monthly", "day_of_week"]},
                },
            },
            handler=handle_get_seasonality,
            toolset="market_data",
        ),
        ToolDefinition(
            name="get_divergences",
            description="Scan for RSI and MACD regular and hidden divergences across multiple timeframes.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframes": {"type": "array", "items": {"type": "string"}},
                },
            },
            handler=handle_get_divergences,
            toolset="market_data",
        ),
        ToolDefinition(
            name="get_market_quote",
            description="Fetch current live bid/ask quote, spread, and broker server time for a symbol.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_market_quote,
            toolset="market_data",
        ),
        ToolDefinition(
            name="get_chart",
            description="Generate a visual candlestick chart for a symbol with optional SMC overlays.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "candles": {"type": "integer"},
                    "smc": {"type": "boolean"},
                },
            },
            handler=handle_get_chart,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_spread_snapshot",
            description="Fetch current live spread and pip size for symbols across the asset universe.",
            parameters={"type": "object", "properties": {"symbols": {"type": "array", "items": {"type": "string"}}}},
            handler=handle_get_spread_snapshot,
            toolset="market_data",
            requires_db=True,
        ),
        ToolDefinition(
            name="plot_equity_curve",
            description="Plot and deliver inline PNG equity curve chart with peak high-water mark and drawdown bands directly into chat (Q013).",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_plot_equity_curve,
            toolset="market_data",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)
