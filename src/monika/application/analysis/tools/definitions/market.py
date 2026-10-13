# ==============================================================================
# File: application/analysis/tools/definitions/market.py
# ==============================================================================

"""
Market data, indicators, price action, TimesFM, and chart tool definitions.
"""

from __future__ import annotations

from monika.application.analysis.tools.definitions.base import _tool

GET_MARKET_SESSION = _tool(
    name="get_market_session",
    description=(
        "Get current active forex market session based on UTC time. "
        "Sessions: Tokyo (00:00-08:00 UTC), London (08:00-16:00 UTC), "
        "New York (13:00-21:00 UTC), London-NY Overlap (13:00-16:00 UTC, highest liquidity). "
        "Session affects volatility patterns and which currency pairs are most active."
    ),
    properties={},
    required=[],
)


GET_PRICE_HISTORY = _tool(
    name="get_price_history",
    description=(
        "Fetch recent OHLCV price history for a specific symbol and timeframe. "
        "Use this to understand recent price action, candle patterns, and momentum."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD', 'GBPUSD').",
        },
        "timeframe": {
            "type": "string",
            "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1", "MN1"],
            "default": "H1",
            "description": "Timeframe for the OHLCV data. Default: 'H1'.",
        },
        "limit": {
            "type": "integer",
            "description": "Number of candles to return (most recent). Default: 50, max: 200.",
        },
        "as_of": {
            "type": "string",
            "description": (
                "Optional ISO timestamp (e.g. '2026-09-30T12:30:00Z' or '2026-09-30 12:30:00') "
                "to fetch historical price bars ending at or before that moment."
            ),
        },
    },
    required=["symbol"],
)


GET_TECHNICAL_INDICATORS = _tool(
    name="get_technical_indicators",
    description=(
        "Fetch pre-calculated technical indicators for a symbol and timeframe. "
        "Returns the latest values of: SMA_20, SMA_50, SMA_200, EMA_20, EMA_50, "
        "RSI_14, MACD (value/signal/histogram), BBANDS (upper/mid/lower/pct_b), STOCH (k/d). "
        "These are computed by the backend engine, not calculated by you."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD').",
        },
        "timeframe": {
            "type": "string",
            "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"],
            "default": "H1",
            "description": "Timeframe for the indicators. Default: 'H1'.",
        },
    },
    required=["symbol"],
)


GET_ATR = _tool(
    name="get_atr",
    description=(
        "Get the Average True Range (ATR) for a symbol and timeframe. "
        "ATR measures market volatility. Use it to validate that your proposed stop loss distance "
        "is reasonable relative to recent volatility (SL should be at least 1.5-2x ATR from entry). "
        "Higher ATR = more volatile = wider SL needed."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {
            "type": "string",
            "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"],
            "default": "H1",
            "description": "Timeframe for ATR calculation. Default: 'H1'.",
        },
    },
    required=["symbol"],
)


GET_MULTI_TIMEFRAME_SUMMARY = _tool(
    name="get_multi_timeframe_summary",
    description=(
        "Composite multi-timeframe analysis: returns technical indicators, swing points, "
        "structure breaks (BOS/ChoCH), and ADX market regime across multiple timeframes (default: M15, H1, H4, D1) in a single unified call. "
        "Saves 6+ round-trips compared to calling each tool individually per timeframe. "
        "Use this FIRST to get a complete multi-timeframe perspective before drilling down."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD')."},
        "timeframes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of timeframes (e.g. ['M15', 'H1', 'H4', 'D1']). Default: ['M15', 'H1', 'H4', 'D1'].",
        },
    },
    required=["symbol"],
)


GET_DXY = _tool(
    name="get_dxy",
    description=(
        "Fetch recent DXY (US Dollar Index) data. "
        "DXY measures USD strength against a basket of 6 major currencies (EUR, JPY, GBP, CAD, SEK, CHF). "
        "DXY rising = USD strengthening = bearish for EURUSD/GBPUSD/AUDUSD/XAUUSD, bullish for USDJPY. "
        "DXY is the master context chart for all USD pairs."
    ),
    properties={
        "days_back": {"type": "integer", "description": "Number of days of DXY history. Default: 10."},
    },
    required=[],
)


SCAN_PATTERN_SIMILARITY = _tool(
    name="scan_pattern_similarity",
    description=(
        "Scan multi-timeframe historical price data (D1, H4, H1) to find chart patterns similar to the "
        "current candlestick segment. Evaluates macroeconomic context (volatility, USD trend, rate cycle, regime) "
        "and analyzes forward outcomes (win rates at 1R/2R/3R, average MFE/MAE, directional bias, and binomial significance). "
        "Use this tool to validate your trade thesis with empirical historical precedent."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD').",
        },
        "timeframes": {
            "type": "array",
            "items": {"type": "string", "enum": ["D1", "H4", "H1"]},
            "description": "Optional list of timeframes to scan. Default: ['D1', 'H4', 'H1'].",
        },
    },
    required=["symbol"],
)


GET_FIBONACCI_LEVELS = _tool(
    name="get_fibonacci_levels",
    description=(
        "Calculate Fibonacci retracement levels based on the most recent significant swing high and swing low. "
        "Returns levels like 0.382, 0.5, 0.618, 0.786 which act as potential reversal zones (Premium/Discount)."
    ),
    properties={
        "symbol": {"type": "string"},
        "timeframe": {"type": "string", "enum": ["H1", "H4", "D1"]},
    },
    required=["symbol", "timeframe"],
)


GET_PRICE_MOMENTUM = _tool(
    name="get_price_momentum",
    description=(
        "Calculate price momentum metrics to assess the degree of 'run-up' before major events. "
        "Returns: pct_change, price_move_absolute, atr_14, run_up_vs_atr, direction, and priced_in_risk_from_momentum. "
        "USE FOR: Priced-In Score Method 3 in the Market Dynamics Framework. "
        "INTERPRETATION of run_up_vs_atr (H4, 20-bar default): "
        "> 4.0 = Very aggressive run-up -> Priced-In score +3 (High risk). "
        "2.5-4.0 = Significant run-up -> Priced-In score +2. "
        "1.5-2.5 = Moderate run-up -> Priced-In score +1. "
        "< 1.5 = Limited pre-positioning -> Priced-In score +0. "
        "For Stage 1 (macro): call with symbol='EURUSD' or 'XAUUSD' as DXY proxy. "
        "For Stage 2 (per-asset): call with the specific asset symbol being analyzed."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY')."},
        "timeframe": {
            "type": "string",
            "description": "Timeframe to calculate momentum (e.g. 'H4', 'D1'). Default: 'H4'.",
        },
    },
    required=["symbol"],
)


GET_CHART = _tool(
    name="get_chart",
    description=(
        "Generate and send a high-resolution candlestick chart image (PNG) for a symbol and timeframe. "
        "Includes volume bars, 20/50 period moving average overlays, and dark theme formatting. "
        "Use this tool when the user asks to 'tampilkan chart/grafik', 'lihat chart XAUUSD', "
        "'show me chart', or requests visual technical analysis."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD').",
        },
        "timeframe": {
            "type": "string",
            "enum": ["M15", "H1", "H4", "D1"],
            "description": "Chart timeframe. Default: 'H4'.",
        },
        "candles": {
            "type": "integer",
            "description": "Number of candles to show on the chart (min: 20, max: 200). Default: 80.",
        },
    },
    required=["symbol"],
)


GET_FUNDING_RATE = _tool(
    name="get_funding_rate",
    description=(
        "Get Bitcoin perpetual futures funding rates from major exchanges (Binance, OKX, Bybit). "
        "Positive rate (>0.01%) = market long-biased -> bullish sentiment but squeeze risk for shorts. "
        "Negative rate (<-0.01%) = market short-biased -> potential short squeeze. "
        "Extreme rates (>0.05% or <-0.05%) = contrarian signal. Also use as Priced-In Score proxy for BTCUSD: "
        "rate > 0.05% = bullish priced-in score +3. rate < -0.05% = bearish priced-in score +3. "
        "CRITICAL for BTCUSD position assessment."
    ),
    properties={},
    required=[],
)


GET_SPREAD_SNAPSHOT = _tool(
    name="get_spread_snapshot",
    description=(
        "Get live or recent broker spread snapshot for trading symbols. "
        "Returns current spread in pips and comparison against typical baseline spread. "
        "Use to evaluate execution slippage risk before placing orders or assessing liquidity."
    ),
    properties={
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of symbols (e.g. ['EURUSD', 'XAUUSD']). Defaults to active asset universe.",
        },
    },
    required=[],
)


GET_MARKET_REGIME = _tool(
    name="get_market_regime",
    description=(
        "Detect current market regime based on ADX. "
        "Pass either 'symbol' (single string) or 'symbols' (array of strings)."
    ),
    properties={
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of symbols (e.g. ['EURUSD', 'XAUUSD']). Also accepts single 'symbol' parameter.",
        },
        "symbol": {
            "type": "string",
            "description": "Single symbol shorthand (e.g. 'XAUUSD'). Use this OR 'symbols', not both.",
        },
        "timeframe": {"type": "string", "description": "Timeframe to check (e.g. 'D1', 'H4'). Default is 'D1'."},
    },
    required=[],  # accepts either 'symbol' or 'symbols'
)


GET_DAILY_RANGE_CONTEXT = _tool(
    name="get_daily_range_context",
    description=(
        "Get Average Daily Range (ADR) context for the intraday strategy. "
        "Returns the required TP band (50-80% of ADR) and max SL (35% of ADR). "
        "Use this to find a mathematically sound structural target. "
        "If today's range is already >85% of ADR, it will warn you to wait."
    ),
    properties={"symbol": {"type": "string", "description": "Trading symbol."}},
    required=["symbol"],
)


GET_OPTIMAL_INTRADAY_LEVELS = _tool(
    name="get_optimal_intraday_levels",
    description=(
        "Computes the best structurally-validated Stop Loss and Take Profit candidates for a "
        "proposed trade, constrained to the intraday ADR target band (50-80% ADR for TP, <=35% "
        "ADR for SL, dynamically scaled by current volatility regime). Scans Order Blocks, FVGs, "
        "S/R zones, liquidity pools, and swing points for real structural levels inside the "
        "mathematically-valid band, ranked by composite score. MANDATORY: call this AFTER "
        "determining direction and entry price, BEFORE finalizing stop_loss/take_profit in "
        "submit_asset_analysis. take_profit MUST be near a top candidate or submission is rejected."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Proposed trade direction."},
        "entry_price": {"type": "number", "description": "Candidate entry price."},
    },
    required=["symbol", "direction", "entry_price"],
)


GET_VOLUME_PROFILE_CONTEXT = _tool(
    name="get_volume_profile_context",
    description="Session-anchored VWAP + 30-day tick-volume profile (POC/VAH/VAL) classifying market as balanced (mean-reverting) or imbalanced (trending). FX tick-volume is a broker activity proxy, not literal traded size.",
    properties={"symbol": {"type": "string"}},
    required=["symbol"],
)


GET_VOLATILITY_REGIME = _tool(
    name="get_volatility_regime",
    description="Analyze market volatility regime, expanding or contracting volatility width (Bollinger-width percentile + Donchian breakout check). chop_block=True blocks new buy/sell entries mechanically unless a breakout is confirmed.",
    properties={"symbol": {"type": "string"}, "timeframe": {"type": "string", "enum": ["H1", "H4", "D1"]}},
    required=["symbol"],
)


GET_TIMESFM_FORECAST = _tool(
    name="get_timesfm_forecast",
    description="Ambil proyeksi harga probabilistik (kuantil 10%, 50%, 90%) menggunakan Google TimesFM 3.0 foundation model.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. XAUUSD, EURUSD)"},
        "timeframe": {
            "type": "string",
            "enum": ["M15", "H1", "H4", "D1"],
            "default": "H1",
            "description": "Timeframe candle untuk forecasting",
        },
        "horizon_steps": {"type": "integer", "default": 24, "description": "Jumlah candle proyeksi ke depan"},
    },
    required=["symbol"],
)


GET_MARKET_CONTEXT = _tool(
    name="get_market_context",
    description=(
        "Composite macro context tool — returns market_session, DXY, VIX, "
        "fundamental_brief, open_positions, and risk_state in a single unified call. "
        "Use this FIRST to fetch all environment context at once."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol for brief and position context."},
    },
    required=["symbol"],
)


GET_TECHNICAL_ANALYSIS = _tool(
    name="get_technical_analysis",
    description=(
        "Composite multi-timeframe technical analysis — returns technical indicators, "
        "structure breaks (BOS/ChoCH), swing points, and SMC zones across D1 and H4 in one call."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD')."},
        "timeframes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Timeframes to analyze. Default: ['D1', 'H4'].",
        },
    },
    required=["symbol"],
)


GET_PRICE_DATA = _tool(
    name="get_price_data",
    description=(
        "Composite price & levels tool — returns recent H4 OHLCV price history, "
        "ATR_14 volatility, and optimal intraday structural TP/SL candidate levels."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "direction": {
            "type": "string",
            "enum": ["buy", "sell"],
            "description": "Optional: trade direction for optimal level optimization.",
        },
        "entry_price": {"type": "number", "description": "Optional: planned entry price for structural level mapping."},
    },
    required=["symbol"],
)


GET_INSTITUTIONAL_DATA = _tool(
    name="get_institutional_data",
    description=(
        "Composite institutional & positioning tool — returns precomputed COT signals, "
        "raw COT report, and asset-specific retail sentiment / funding rate / fear & greed."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "cot_code": {"type": "string", "description": "Optional COT market code (e.g. '088691' for Gold)."},
    },
    required=["symbol"],
)


GET_VERIFIED_MARKET_SNAPSHOT = _tool(
    name="get_verified_market_snapshot",
    description=(
        "Deterministic ground-truth market snapshot. Computes latest verified OHLCV bar, "
        "RSI, MACD, ATR, EMA (20/50/200), and key S/R levels directly from verified data. "
        "THIS IS SACRED GROUND TRUTH: LLM must treat these numbers as exact and never hallucinate price levels."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument symbol (e.g. 'EURUSD', 'XAUUSD', 'BTCUSD')."}
    },
    required=["symbol"],
)


GET_MARKET_QUOTE = _tool(
    name="get_market_quote",
    description=(
        "Get current market quote (live tick or latest price) for a trading symbol. "
        "Returns current price, bid, ask, spread, and timestamp. "
        "Useful for verifying current entry price, spread, or market levels."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading instrument symbol (e.g. 'EURUSD', 'XAUUSD', 'GBPUSD', 'BTCUSD').",
        }
    },
    required=["symbol"],
)


PLOT_PRICE_CHART = _tool(
    name="plot_price_chart",
    description=(
        "Plot a high-resolution dark-theme candlestick chart with SMC overlays (Fair Value Gap boxes & Swing Pivots). "
        "Saves the resulting PNG image to disk and delivers it directly to the user's interface."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'XAUUSD', 'EURUSD')."},
        "timeframe": {
            "type": "string",
            "description": "Candle timeframe ('M5', 'M15', 'H1', 'H4', 'D1'). Default: 'H1'.",
        },
        "candles": {"type": "integer", "description": "Number of recent candles to plot (default: 80)."},
        "overlay_smc": {
            "type": "boolean",
            "description": "Whether to render FVG boxes and swing pivot markers (default: true).",
        },
    },
    required=["symbol"],
)


DETECT_CANDLESTICK_PATTERNS = _tool(
    name="detect_candlestick_patterns",
    description=(
        "Detect classical price action candlestick patterns: Pin Bar / Hammer, Shooting Star, "
        "Bullish/Bearish Engulfing, Doji (Dragonfly/Gravestone), Morning Star, Evening Star."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "description": "Candle timeframe ('M15', 'H1', 'H4'). Default: 'H1'."},
        "lookback": {"type": "integer", "description": "Number of recent candles to analyze (default: 10)."},
    },
    required=["symbol"],
)


GET_SYNTHETIC_CROSS_RATE = _tool(
    name="get_synthetic_cross_rate",
    description="Calculate synthetic cross-rate, spread, and synthetic ATR from USD-based majors for non-universe pairs (e.g. GBPJPY, EURGBP, EURJPY, AUDJPY, EURAUD, GBPAUD).",
    properties={
        "pair": {
            "type": "string",
            "description": "Cross pair to synthesize (e.g. 'GBPJPY', 'EURGBP', 'EURJPY', 'AUDJPY').",
        },
        "timeframe": {"type": "string", "description": "Timeframe for ATR calculation (e.g. 'H1', 'H4', 'D1')."},
    },
    required=["pair"],
)


SIMULATE_PRICE_SHOCK_TOOL = _tool(
    name="simulate_price_shock",
    description="Simulate price shock on portfolio equity and open positions (stress test).",
    properties={
        "symbol": {"type": "string", "description": "Symbol to shock (e.g. 'XAUUSD', 'EURUSD')."},
        "pct_change": {"type": "number", "description": "Percentage change to shock (e.g. -5.0 or 2.5)."},
    },
    required=["symbol", "pct_change"],
)


GET_SYMBOL_SPECIFICATION = _tool(
    name="get_symbol_specification",
    description="Get exact instrument specifications including contract size, pip size, pip value in USD, digits, and lot limits.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Symbol name or shorthand (e.g. 'XAUUSD', 'EURUSD', 'BTCUSD', 'US30').",
        },
    },
    required=["symbol"],
)


GET_SMT_DIVERGENCE = _tool(
    name="get_smt_divergence",
    description="Detect Smart Money Technique (SMT) divergence between correlated or inversely correlated pairs (e.g. EURUSD vs DXY).",
    properties={
        "symbol": {"type": "string", "description": "Primary trading symbol (e.g. 'EURUSD')."},
        "compared_to": {"type": "string", "description": "Benchmark or correlated asset (e.g. 'DXY', 'GBPUSD')."},
        "timeframe": {"type": "string", "description": "Candle timeframe (e.g. 'H1', 'H4')."},
        "lookback": {"type": "integer", "description": "Lookback bars (default 30)."},
    },
    required=["symbol"],
)


GET_PIVOT_POINTS = _tool(
    name="get_pivot_points",
    description="Calculate Classic, Camarilla, and Woodie pivot points, support (S1-S4), and resistance (R1-R4) levels for a given symbol.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD'). Defaults to watchlist primary.",
        },
        "timeframe": {
            "type": "string",
            "enum": ["D1", "W1", "M1"],
            "description": "Base calculation timeframe (default: 'D1').",
        },
        "method": {
            "type": "string",
            "enum": ["all", "classic", "camarilla", "woodie"],
            "description": "Pivot calculation formula (default: 'all').",
        },
    },
    required=[],
)


GET_ICHIMOKU = _tool(
    name="get_ichimoku",
    description="Compute full Ichimoku Kinko Hyo cloud indicator: Tenkan-sen (Conversion), Kijun-sen (Base), Senkou Span A/B (Cloud), and Chikou Span (Lagging).",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["M15", "M30", "H1", "H4", "D1"],
            "description": "Chart timeframe (default: 'H1').",
        },
        "tenkan": {"type": "integer", "description": "Tenkan period (default: 9)."},
        "kijun": {"type": "integer", "description": "Kijun period (default: 26)."},
        "senkou_b": {"type": "integer", "description": "Senkou Span B period (default: 52)."},
    },
    required=[],
)


SCAN_CHART_PATTERNS = _tool(
    name="scan_chart_patterns",
    description="Scan price action for classic and harmonic chart patterns: Double Top/Bottom, Head and Shoulders / Inverse H&S, Gartley, Bat, Butterfly, and Crab.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["M15", "H1", "H4", "D1"],
            "description": "Chart timeframe (default: 'H1').",
        },
        "lookback": {"type": "integer", "description": "Number of bars to analyze (default: 150)."},
    },
    required=[],
)


GET_SEASONALITY = _tool(
    name="get_seasonality",
    description="Calculate historical seasonality statistics: monthly returns, day-of-week win rates, and calendar tendencies across multi-year historical data.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["monthly", "day_of_week", "all"],
            "description": "Seasonality analysis grouping (default: 'all').",
        },
        "years": {"type": "integer", "description": "Historical lookback in years (default: 5)."},
    },
    required=[],
)


GET_DIVERGENCES = _tool(
    name="get_divergences",
    description="Detect regular and hidden momentum divergences between price swings and technical oscillators (RSI, MACD, Stochastic).",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["M15", "H1", "H4", "D1"],
            "description": "Chart timeframe (default: 'H1').",
        },
        "indicator": {
            "type": "string",
            "enum": ["all", "rsi", "macd", "stochastic"],
            "description": "Oscillator indicator to evaluate (default: 'all').",
        },
    },
    required=[],
)


GET_RECENT_TICK_FLOW = _tool(
    name="get_recent_tick_flow",
    description="Retrieve recent high-frequency tick data flow: Bid/Ask spread, tick volume, micro-delta, and buy/sell pressure ratio directly from MT5.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "count": {"type": "integer", "description": "Number of recent ticks to inspect (default: 100, max: 1000)."},
    },
    required=[],
)


EXPORT_TICK_DATA = _tool(
    name="export_tick_data",
    description="Export historical raw tick data to CSV file and prepare download link for quantitative tick analysis.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "hours": {"type": "integer", "description": "Number of hours of tick history to export (default: 4, max: 24)."},
        "filename": {"type": "string", "description": "Optional custom export filename."},
    },
    required=[],
)


GET_COMMODITY_SPREAD_TOOL = _tool(
    name="get_commodity_spread",
    description="Calculates live commodity spreads (Brent vs WTI crude oil), 20-day rolling mean, and z-score for stat-arb (Q088).",
    properties={
        "primary_symbol": {"type": "string", "description": "Primary commodity (default: 'XBRUSD')."},
        "secondary_symbol": {"type": "string", "description": "Secondary commodity (default: 'XTIUSD')."},
    },
    required=[],
)


GET_MT5_CHART_OBJECTS_TOOL = _tool(
    name="get_mt5_chart_objects",
    description="Extract user-drawn S/R lines, trendlines, Fibonacci levels, and indicator parameters from the active MT5 chart (Q151).",
    properties={"symbol": {"type": "string", "description": "Chart instrument symbol (default: 'XAUUSD')."}},
    required=[],
)


CAPTURE_MT5_CHART_SCREENSHOT_TOOL = _tool(
    name="capture_mt5_chart_screenshot",
    description="Capture an on-demand screenshot of the active MT5 chart window and prepare it for Multimodal Vision inspection (Q151).",
    properties={
        "symbol": {"type": "string", "description": "Chart instrument symbol (default: 'XAUUSD')."},
        "timeframe": {"type": "string", "description": "Chart timeframe (default: 'H1')."},
        "width": {"type": "integer", "description": "Image width in pixels (default: 1280)."},
        "height": {"type": "integer", "description": "Image height in pixels (default: 720)."},
    },
    required=[],
)


PLOT_EQUITY_CURVE_TOOL = _tool(
    name="plot_equity_curve",
    description="Plot and deliver inline PNG equity curve chart with drawdown bands directly into Telegram chat (Q013).",
    properties={"days_back": {"type": "integer", "description": "Historical days back to plot (default: 90)."}},
    required=[],
)


__all__ = [
    "GET_MARKET_SESSION",
    "GET_PRICE_HISTORY",
    "GET_TECHNICAL_INDICATORS",
    "GET_ATR",
    "GET_MULTI_TIMEFRAME_SUMMARY",
    "GET_DXY",
    "SCAN_PATTERN_SIMILARITY",
    "GET_FIBONACCI_LEVELS",
    "GET_PRICE_MOMENTUM",
    "GET_CHART",
    "GET_FUNDING_RATE",
    "GET_SPREAD_SNAPSHOT",
    "GET_MARKET_REGIME",
    "GET_DAILY_RANGE_CONTEXT",
    "GET_OPTIMAL_INTRADAY_LEVELS",
    "GET_VOLUME_PROFILE_CONTEXT",
    "GET_VOLATILITY_REGIME",
    "GET_TIMESFM_FORECAST",
    "GET_MARKET_CONTEXT",
    "GET_TECHNICAL_ANALYSIS",
    "GET_PRICE_DATA",
    "GET_INSTITUTIONAL_DATA",
    "GET_VERIFIED_MARKET_SNAPSHOT",
    "GET_MARKET_QUOTE",
    "PLOT_PRICE_CHART",
    "DETECT_CANDLESTICK_PATTERNS",
    "GET_SYNTHETIC_CROSS_RATE",
    "SIMULATE_PRICE_SHOCK_TOOL",
    "GET_SYMBOL_SPECIFICATION",
    "GET_SMT_DIVERGENCE",
    "GET_PIVOT_POINTS",
    "GET_ICHIMOKU",
    "SCAN_CHART_PATTERNS",
    "GET_SEASONALITY",
    "GET_DIVERGENCES",
    "GET_RECENT_TICK_FLOW",
    "EXPORT_TICK_DATA",
    "GET_COMMODITY_SPREAD_TOOL",
    "GET_MT5_CHART_OBJECTS_TOOL",
    "CAPTURE_MT5_CHART_SCREENSHOT_TOOL",
    "PLOT_EQUITY_CURVE_TOOL",
]
