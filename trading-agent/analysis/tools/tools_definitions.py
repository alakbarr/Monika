# ==============================================================================
# File: analysis/tools_definitions.py
# ==============================================================================

"""
Definisi JSON Schema Tools untuk AI Trading Agent.

Prinsip Keamanan (Spesifikasi §1):
- Tool 'READ' (baca data) bisa diakses LLM.
- Tool 'WRITE' (eksekusi order finansial) DILARANG KERAS diakses LLM.
- Interaksi LLM menulis ke sistem HANYA via `submit_fundamental_brief` dan `submit_asset_analysis`. Eksekusi riil (MT5) diurus 100% oleh backend (non-AI).
"""

from typing import Any

from analysis.schemas.schemas import get_tool_schema

from analysis.schemas.schemas import SubmitFundamentalBriefSchema, SubmitAssetAnalysisSchema
# Helper Function for Tool Generation
# =============================================================================

def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Fungsi helper pencetak JSON Schema (Anthropic format)."""
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


# =============================================================================
# Tahap 1 — Fundamental Brief Tools (read)
# =============================================================================

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

GET_ECONOMIC_CALENDAR = _tool(
    name="get_economic_calendar",
    description=(
        "Fetch upcoming and recent economic events from the calendar. "
        "Returns event name, currency, impact level, actual/forecast/previous values, "
        "and scheduled time. Use this to understand what macro events are upcoming or "
        "what data was just released. Use 'event_name' to search for specific releases (e.g. 'PCE', 'CPI', 'NFP')."
    ),
    properties={
        "event_name": {
            "type": "string",
            "description": "Optional keyword or event name to search (e.g. 'PCE', 'CPI', 'Nonfarm Payrolls', 'GDP').",
        },
        "impact_filter": {
            "type": "string",
            "enum": ["all", "high", "medium", "high_and_medium"],
            "description": "Filter events by impact level. Default: 'high_and_medium'.",
        },
        "currency_filter": {
            "type": "string",
            "description": "Optional: comma-separated currency codes to filter (e.g. 'USD,EUR'). Leave empty for all.",
        },
        "hours_ahead": {
            "type": "integer",
            "description": "How many hours ahead to look for upcoming events. Default: 48.",
        },
        "hours_behind": {
            "type": "integer",
            "description": "How many hours behind to look for recent events. Default: 24 (expands to 168 if event_name is specified).",
        },
    },
    required=[],
)

GET_WEEKLY_MACRO_SUMMARY = _tool(
    name="get_weekly_macro_summary",
    description=(
        "Generate a comprehensive weekly macroeconomic summary covering key high-impact events for the upcoming week, "
        "DXY trend, VIX regime, FedWatch rate probabilities, US Treasury yields, and monetary policy outlook."
    ),
    properties={
        "currencies": {
            "type": "string",
            "description": "Optional comma-separated currencies to prioritize (e.g. 'USD,EUR,GBP,JPY'). Default: all major currencies.",
        },
        "days_ahead": {
            "type": "integer",
            "description": "Lookahead horizon in days. Default: 7.",
        },
    },
    required=[],
)

GET_NEWS_DIGEST = _tool(
    name="get_news_digest",
    description=(
        "Get a pre-processed news digest summarizing all significant market news from the last N hours. "
        "This is more efficient than get_news_items as it provides a condensed narrative. "
        "Use this FIRST for Stage 1 macro context, then use get_news_items for specific details if needed."
    ),
    properties={
        "hours_back": {"type": "integer", "description": "Period to cover. Default: 12."},
    },
    required=[],
)

GET_NEWS_ITEMS = _tool(
    name="get_news_items",
    description=(
        "Fetch recent news items from all sources (TradingView, Kitco, RSS feeds, Twitter). "
        "Use this to understand current market sentiment and fundamental drivers. "
        "Filter by currency or search by specific keyword (e.g. 'gold', 'oil', 'rate hike', 'fomc')."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Optional search keyword or topic (e.g. 'gold', 'emas', 'oil', 'Powell', 'PCE', 'inflation').",
        },
        "limit": {
            "type": "integer",
            "description": "Number of news items to return. Default: 30, max: 100.",
        },
        "currency_filter": {
            "type": "string",
            "description": "Optional: comma-separated currency/asset tags (e.g. 'USD,XAU'). Leave empty for all.",
        },
        "hours_back": {
            "type": "integer",
            "description": "Only return news from the last N hours. Default: 24 (or 168 if query is specified).",
        },
        "source_filter": {
            "type": "string",
            "description": "Optional: specific source name (e.g. 'rss_bloomberg', 'twitter', 'kitco').",
        },
    },
    required=[],
)

GET_TREASURY_YIELDS = _tool(
    name="get_treasury_yields",
    description=(
        "Fetch current US Treasury yield curve data (2Y, 5Y, 10Y, 30Y). "
        "Use this to assess the yield curve shape (normal/inverted), interest rate expectations, "
        "and risk-off vs risk-on sentiment. Inverted 2Y-10Y spread historically signals recession risk."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Return yield data for the last N days (for trend analysis). Default: 5.",
        },
    },
    required=[],
)

GET_BOND_YIELD_SPREADS = _tool(
    name="get_bond_yield_spreads",
    description=(
        "Fetch international government bond yield spreads vs US Treasury (US-DE Bund, US-UK Gilt, US-JP JGB, US-AU Bond) "
        "for BOTH 2-Year (monetary policy short-end) and 10-Year (economic benchmark) tenors. "
        "Yield differentials are the #1 fundamental macro driver for Forex pairs: "
        "US-DE spread drives EURUSD direction, US-UK spread drives GBPUSD, US-JP spread drives USDJPY, US-AU spread drives AUDUSD. "
        "Short-end 2Y spreads reflect policy divergence; widening US-DE 2Y spread = USD yield advantage increases = bearish EURUSD. "
        "Narrowing US-DE 2Y spread = EUR strengthens = bullish EURUSD. "
        "Also provides spread momentum and inversion status."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Number of days of spread history. Default: 10.",
        },
    },
    required=[],
)

GET_INTEREST_RATES = _tool(
    name="get_interest_rates",
    description=(
        "Fetch current official central bank interest rates (FED, ECB, BOE, BOJ, RBA). "
        "Use this to understand rate differentials between currencies and the monetary policy stance."
    ),
    properties={},
    required=[],
)

GET_FEDWATCH_PROBABILITIES = _tool(
    name="get_fedwatch_probabilities",
    description=(
        "Fetch CME FedWatch probabilities for upcoming Fed meeting decisions "
        "(hold, cut 25bp, cut 50bp, hike 25bp, etc.). "
        "Supports temporal comparison before and after news/events via 'event_time' or 'compare_hours_ago', "
        "as well as specific meeting filtering via 'meeting_date' and full historical trajectory via 'include_history'. "
        "Use this to gauge market expectations AND to assess DEGREE OF PRICED-IN for Fed policy changes. "
        "PRICED-IN INTERPRETATION (use dominant outcome probability): "
        "priced_in_degree > 0.90 = Fully Priced In (score 9-10) → very high sell-the-news risk. "
        "priced_in_degree 0.75-0.90 = Largely Priced In (score 7-8) → high sell-the-news risk. "
        "priced_in_degree 0.55-0.75 = Partially Priced In (score 5-6) → event reaction uncertain. "
        "priced_in_degree 0.35-0.55 = Weakly Priced In (score 3-4) → post-event move likely large. "
        "priced_in_degree < 0.35 = NOT Priced In (score 1-2) → genuine surprise risk, avoid pre-positioning. "
        "ALSO CHECK: rapid probability shift (e.g., 40% → 87% in 2 weeks) = aggressive market repricing → add +1 to score."
    ),
    properties={
        "meeting_date": {
            "type": "string",
            "description": "Optional specific meeting date filter (e.g. '28 Oct26', '9 Dec26', 'Oct 2026').",
        },
        "compare_hours_ago": {
            "type": "number",
            "description": "Compare current probabilities with snapshot from N hours ago (e.g. 2, 4, 12, 24). Automatically computes deltas and shift summary.",
        },
        "event_time": {
            "type": "string",
            "description": "ISO timestamp of a news or economic release (e.g. '2026-09-30T12:30:00Z'). Automatically compares pre-event vs post-event probabilities.",
        },
        "include_history": {
            "type": "boolean",
            "description": "Whether to include historical trajectory list of past probability snapshots.",
        },
        "limit": {
            "type": "integer",
            "description": "Number of upcoming meetings to return. Default: 3.",
        },
    },
    required=[],
)

GET_CENTRAL_BANK_EXPECTATIONS = _tool(
    name="get_central_bank_expectations",
    description=(
        "Fetch market-implied rate decision expectations (probabilities of Rate Hike, Hold, Rate Cut) "
        "and scheduled meeting dates across major central banks (FED, ECB, BOE, BOJ, RBA). "
        "Also provides degree of priced-in score (1-10), policy bias, and temporal before/after comparison."
    ),
    properties={
        "bank": {
            "type": "string",
            "description": "Optional central bank code: FED, ECB, BOE, BOJ, RBA. Omit to return all 5 banks.",
        },
        "compare_hours_ago": {
            "type": "number",
            "description": "Compare expectations with snapshot from N hours ago.",
        },
        "event_time": {
            "type": "string",
            "description": "ISO timestamp to compare pre-event vs post-event rate expectations.",
        },
        "include_history": {
            "type": "boolean",
            "description": "Whether to return historical expectation snapshots.",
        },
    },
    required=[],
)

GET_COT_REPORT = _tool(
    name="get_cot_report",
    description=(
        "Fetch CFTC Commitments of Traders (COT) report data for specified markets. "
        "Shows positioning of dealers, asset managers, and leveraged funds (hedge funds). "
        "Use leveraged funds net position for Priced-In Score Method 2. "
        "EXTREME POSITIONING THRESHOLDS (industry-standard absolute benchmarks): "
        "Gold (088691): leveraged_net > +200K = extreme long (overcrowded bullish). leveraged_net < -80K = extreme short. "
        "EUR/USD (099741): leveraged_net > +150K or < -150K = extreme (overcrowded). "
        "GBP/USD (096742): leveraged_net > +80K or < -80K = extreme. "
        "JPY (097741): leveraged_net > +60K or < -80K = extreme. "
        "AUD (232741): leveraged_net > +60K or < -60K = extreme. "
        "Available markets: gold (088691), euro_fx (099741), british_pound (096742), "
        "japanese_yen (097741), australian_dollar (232741)."
    ),
    properties={
        "market_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of market codes to fetch. E.g. ['088691', '099741']. Leave empty for all configured markets.",
        },
        "weeks_back": {
            "type": "integer",
            "description": "Number of weekly reports to fetch (1-12) to observe historical institutional positioning trends. Default: 1.",
        },
    },
    required=[],
)

GET_VIX = _tool(
    name="get_vix",
    description=(
        "Fetch recent VIX (CBOE Volatility Index) data. "
        "VIX >30 = high fear/risk-off. VIX 15-30 = elevated uncertainty. VIX <15 = complacency/risk-on. "
        "Use this to calibrate overall market risk sentiment."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Return VIX data for the last N trading days. Default: 10.",
        },
    },
    required=[],
)

GET_EIA_OIL_INVENTORY = _tool(
    name="get_eia_oil_inventory",
    description=(
        "Get US crude oil commercial inventory data from EIA (weekly). "
        "Inventory build (positive WoW change) = bearish for oil price. "
        "Inventory draw (negative WoW change) = bullish for oil price. "
        "Surprise vs analyst consensus is the key market mover. "
        "Released every Wednesday ~10:30 AM ET. Highly relevant for XTIUSD analysis."
    ),
    properties={},
    required=[],
)

GET_FEAR_GREED = _tool(
    name="get_fear_greed_index",
    description=(
        "Get the current Crypto Fear & Greed Index (0-100) from alternative.me. "
        "Useful as supplementary risk sentiment gauge alongside VIX. "
        "0-25 = Extreme Fear (contrarian buy zone), 25-45 = Fear, "
        "45-55 = Neutral, 55-75 = Greed, 75-100 = Extreme Greed (potential reversal). "
        "Highly relevant for BTCUSD analysis. Also correlates with general risk-on/off."
    ),
    properties={},
    required=[],
)

_fundamental_brief_schema = get_tool_schema(SubmitFundamentalBriefSchema)

SUBMIT_FUNDAMENTAL_BRIEF = _tool(
    name="submit_fundamental_brief",
    description=(
        "Submit your completed fundamental analysis brief. "
        "Call this ONCE after you have gathered all necessary data and formed your analysis. "
        "This saves the structured brief to the database for use in the per-asset analysis stage. "
        "WAJIB mengisi field 'priced_in_assessment' secara komprehensif, jangan pernah dibiarkan kosong. "
        "Do NOT submit until you are confident in your analysis."
    ),
    properties=_fundamental_brief_schema["properties"],
    required=_fundamental_brief_schema.get("required", []),
)


# =============================================================================
# Tahap 2 — Per-Asset Analysis Tools (read)
# =============================================================================

GET_FUNDAMENTAL_BRIEF = _tool(
    name="get_fundamental_brief",
    description=(
        "Fetch the most recent fundamental brief generated in Stage 1 analysis. "
        "This gives you the macro context (currency biases, risk sentiment, key risks) "
        "to inform your per-asset technical analysis."
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
            "description": "Optional list of timeframes (e.g. ['M15', 'H1', 'H4', 'D1']). Default: ['M15', 'H1', 'H4', 'D1']."
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

GET_ECONOMIC_SURPRISE = _tool(
    name="get_economic_surprise",
    description=(
        "Get economic data surprise scores — how much recent actual data beat or missed forecasts. "
        "Positive score = beat (bullish for currency), Negative score = miss (bearish). "
        "Useful for assessing underlying momentum of an economy beyond just the current data point."
    ),
    properties={
        "currency": {"type": "string", "description": "Currency code (e.g. 'USD', 'EUR', 'GBP')"},
        "days_back": {"type": "integer", "description": "How many days back to look. Default: 14."},
    },
    required=["currency"],
)

GET_SWING_POINTS = _tool(
    name="get_swing_points",
    description=(
        "Fetch detected swing high and swing low points for a symbol and timeframe. "
        "Use these to identify market structure: higher highs/lows (uptrend), "
        "lower highs/lows (downtrend), or ranges."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "limit": {"type": "integer", "description": "Number of most recent swing points per type. Default: 10."},
    },
    required=["symbol", "timeframe"],
)

GET_SR_ZONES = _tool(
    name="get_sr_zones",
    description=(
        "Fetch Support & Resistance zones for a symbol and timeframe. "
        "Zones are clustered swing points with multiple touches — stronger zones have higher strength values. "
        "Use these as potential entry, target, or invalidation levels."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "min_strength": {"type": "integer", "description": "Minimum number of touches to include. Default: 2."},
    },
    required=["symbol", "timeframe"],
)

GET_LIQUIDITY_ZONES = _tool(
    name="get_liquidity_zones",
    description=(
        "Fetch liquidity zones — areas above swing highs (buy-stop clusters) and "
        "below swing lows (sell-stop clusters) where retail stop-losses are likely concentrated. "
        "In SMC/ICT analysis, price often sweeps these zones before reversing. "
        "Use to identify likely sweep targets and potential reversal zones."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
    },
    required=["symbol", "timeframe"],
)

GET_FVG_ZONES = _tool(
    name="get_fvg_zones",
    description=(
        "Fetch Fair Value Gap (FVG) zones — price imbalances where candle N-2 and candle N "
        "did not overlap (3-candle pattern). Unfilled FVGs often act as magnets for price. "
        "Bullish FVG = potential support. Bearish FVG = potential resistance."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "filled": {
            "type": "boolean",
            "description": "If false (default), only return unfilled FVGs. If true, include filled ones.",
        },
    },
    required=["symbol", "timeframe"],
)

GET_ORDER_BLOCKS = _tool(
    name="get_order_blocks",
    description=(
        "Fetch unmitigated Order Blocks (OB) for a symbol and timeframe. "
        "Order blocks are the last opposite candle before a strong impulsive move. "
        "Unmitigated OBs often act as strong support/resistance where institutional orders are placed."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "days": {"type": "integer", "description": "Maximum age of order blocks in days (default: 14)."},
        "limit": {"type": "integer", "description": "Maximum number of blocks to return (default: 10)."},
    },
    required=["symbol", "timeframe"],
)

# Composite SMC zones tool: replaces 4 separate calls with 1.
# Returns order_blocks + fvg_zones + liquidity_zones + sr_zones in a single payload.
# Use this instead of calling each tool individually to save ~3 round-trips per asset.
GET_SMC_ZONES = _tool(
    name="get_smc_zones",
    description=(
        "Composite SMC/ICT analysis tool — returns Order Blocks, FVG Zones, "
        "Liquidity Zones, and S/R Zones in a single call. "
        "Use this instead of calling get_order_blocks + get_fvg_zones + "
        "get_liquidity_zones + get_sr_zones separately — saves 3 round-trips. "
        "Order Blocks: unmitigated institutional entry zones. "
        "FVG Zones: price imbalances (unfilled by default). "
        "Liquidity Zones: stop-loss clusters above highs / below lows. "
        "S/R Zones: clustered swing points with multiple touches."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["H1", "H4", "D1"]},
        "include_filled_fvg": {
            "type": "boolean",
            "description": "If true, include already-filled FVGs. Default: false.",
        },
        "min_sr_strength": {
            "type": "integer",
            "description": "Minimum touch count for S/R zones. Default: 2.",
        },
    },
    required=["symbol", "timeframe"],
)


GET_STRUCTURE_BREAKS = _tool(
    name="get_structure_breaks",
    description=(
        "Fetch recent Break of Structure (BOS) and Change of Character (ChoCH) events. "
        "BOS indicates trend continuation, while ChoCH indicates a potential trend reversal."
    ),
    properties={
        "symbol": {"type": "string"},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
    },
    required=["symbol", "timeframe"],
)

GET_INDUCEMENTS = _tool(
    name="get_inducements",
    description=(
        "Detect Inducement (IDM) price level and validation status based on SMC rules. "
        "In bullish trend, IDM is the first internal swing low after a new high. "
        "When price sweeps IDM, the high is confirmed and valid order blocks below can be safely traded."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"], "description": "Timeframe to evaluate (default: 'M15')."},
        "trend": {"type": "string", "enum": ["bullish", "bearish"], "description": "Current directional trend bias."},
    },
    required=["symbol"],
)

GET_BREAKER_BLOCKS = _tool(
    name="get_breaker_blocks",
    description=(
        "Detect Breaker Blocks: failed order blocks that were aggressively broken through with strong momentum, "
        "inverting their polarity (failed bullish OB becomes resistance; failed bearish OB becomes support)."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
    },
    required=["symbol", "timeframe"],
)

GET_INVERTED_FVG = _tool(
    name="get_inverted_fvg",
    description=(
        "Detect Inverted Fair Value Gaps (IFVG): Fair Value Gaps that were violated and closed through with displacement, "
        "inverting their institutional polarity (broken bullish FVG becomes resistance; broken bearish FVG becomes support)."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"], "description": "Timeframe (default: 'H1')."},
        "lookback": {"type": "integer", "description": "Lookback bars (default: 150)."}
    },
    required=["symbol"],
)


GET_JUDAS_SWING = _tool(
    name="get_judas_swing",
    description=(
        "Detect London Open (08:00 UTC) Judas Swing false breakout trap. "
        "Identifies false expansions that engineer liquidity above/below Asian range extremes before aggressive reversal."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'GBPUSD', 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1"], "description": "Timeframe for microstructure (default: 'M15')."},
    },
    required=["symbol"],
)

GET_EQUAL_HIGHS_LOWS = _tool(
    name="get_equal_highs_lows",
    description=(
        "Detect engineered liquidity pools formed by Equal Highs (EQH / Buy-Side Liquidity) "
        "or Equal Lows (EQL / Sell-Side Liquidity) within tight tolerance pips."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "tolerance_pips": {"type": "number", "description": "Price clustering tolerance in pips (default: 3.0)."},
    },
    required=["symbol", "timeframe"],
)

GET_WICK_TO_WICK_FVG = _tool(
    name="get_wick_to_wick_fvg",
    description=(
        "Detect shadow / wick-to-wick Fair Value Gaps where long overlapping wicks form an imbalance on HTF."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"]},
    },
    required=["symbol", "timeframe"],
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

GET_PRECOMPUTED_COT_SIGNALS = _tool(
    name="get_precomputed_cot_signals",
    description=(
        "Fetch pre-computed COT signals. This provides a simplified view of institutional positioning, "
        "including net positions and extreme sentiment flags (e.g. 'extreme_long')."
    ),
    properties={},
    required=[],
)

GET_SURPRISE_SUMMARY = _tool(
    name="get_surprise_summary",
    description=(
        "Fetch aggregated economic surprise scores per currency for the last 2 weeks. "
        "Use this to determine macro momentum for a specific currency."
    ),
    properties={},
    required=[],
)

INSPECT_ECONOMIC_REPORT = _tool(
    name="inspect_economic_report",
    description=(
        "Decompose macroeconomic releases (CPI, NFP, PCE, PPI, JOLTS, ISM) into granular sub-components. "
        "Identifies top upside/downside drivers, separates transitory noise from persistent sticky core inflation, "
        "and evaluates labor market quality including 2-month net revisions drag and household survey divergence."
    ),
    properties={
        "report_type": {"type": "string", "description": "CPI, NFP, PCE, PPI, JOLTS, ISM_MANUFACTURING, ISM_SERVICES, UMICH"},
        "period": {"type": "string", "description": "Period string e.g. 2026-09 or 2026-Q3"},
        "country": {"type": "string", "description": "Country code e.g. US, EU, UK, JP"},
        "currency": {"type": "string", "description": "Currency e.g. USD, EUR, GBP, JPY"},
    },
    required=[],
)

DIFF_CENTRAL_BANK_DOCUMENTS = _tool(
    name="diff_central_bank_documents",
    description=(
        "Perform sentence-level redline diffing between consecutive central bank monetary statements and meeting minutes "
        "(Federal Reserve, ECB, BoE, BoJ). Extracts additions, deletions, phrase substitutions, and calculates net "
        "hawkish vs dovish tone shift score (-1.0 to +1.0)."
    ),
    properties={
        "bank": {"type": "string", "description": "Central bank: FED, ECB, BOE, BOJ"},
        "doc_type": {"type": "string", "description": "Document type: MINUTES, STATEMENT, BEIGE_BOOK"},
    },
    required=[],
)

GET_MACRO_CROSS_REPORT_SYNTHESIS = _tool(
    name="get_macro_cross_report_synthesis",
    description=(
        "Synthesize the complete macroeconomic pipeline: ISM Prices Paid -> PPI -> CPI -> Core PCE -> "
        "NFP Wage Growth -> Fed Dot Plot Expectations -> Treasury Yields & US Dollar Index (DXY) direction."
    ),
    properties={
        "currency": {"type": "string", "description": "Currency code e.g. USD"},
        "lookback_days": {"type": "integer", "description": "Lookback window in days (default 30)"},
    },
    required=[],
)

GET_G10_MACRO_DIVERGENCE = _tool(
    name="get_g10_macro_divergence",
    description=(
        "Evaluate relative macroeconomic divergence, interest rate differentials, inflation momentum, "
        "and growth trajectory between G10 currency pairs (EURUSD, USDJPY, GBPUSD, AUDUSD)."
    ),
    properties={
        "pair": {"type": "string", "description": "Currency pair symbol e.g. EURUSD, USDJPY, GBPUSD"},
    },
    required=["pair"],
)

GET_FED_NET_LIQUIDITY_AND_STRESS = _tool(
    name="get_fed_net_liquidity_and_stress",
    description=(
        "Fetch weekly Federal Reserve Net Systemic Liquidity (WALCL - TGA - RRP), corporate credit spreads "
        "(ICE BofA High Yield OAS), and interbank money market funding stress (SOFR). Identifies macro liquidity regimes."
    ),
    properties={
        "lookback_weeks": {"type": "integer", "description": "Number of weeks to evaluate (default 8)"},
    },
    required=[],
)

GET_TREASURY_AUCTION_RESULTS = _tool(
    name="get_treasury_auction_results",
    description=(
        "Inspect US Treasury debt auction outcomes (2Y, 5Y, 10Y, 30Y notes/bonds) including stopping yield, "
        "auction tail spread in basis points, bid-to-cover ratio, and foreign indirect bidder demand percentage."
    ),
    properties={
        "tenor": {"type": "string", "description": "Auction tenor: 2Y, 5Y, 10Y, 30Y (default 10Y)"},
        "limit": {"type": "integer", "description": "Number of recent auctions (default 5)"},
    },
    required=[],
)

GET_ECB_QT_PROGRESS = _tool(
    name="get_ecb_qt_progress",
    description=(
        "Track European Central Bank (ECB) total balance sheet trend, Quantitative Tightening (QT) progress, "
        "asset contraction rate, APP passive runoff status, and PEPP reinvestment phase-out implications."
    ),
    properties={
        "lookback_weeks": {"type": "integer", "description": "Number of weeks to evaluate (default 8)"},
    },
    required=[],
)

GET_GLOBAL_PMI_TREND = _tool(
    name="get_global_pmi_trend",
    description=(
        "Track global and regional manufacturing PMIs (JPMorgan Global, US, Eurozone, UK, China Caixin), "
        "expansion vs contraction diffusion regime (>50 vs <50), and macroeconomic manufacturing divergence."
    ),
    properties={
        "period": {"type": "string", "description": "Period e.g. '2026-09' (optional)"},
    },
    required=[],
)

_asset_analysis_schema = get_tool_schema(SubmitAssetAnalysisSchema)

SUBMIT_ASSET_ANALYSIS = _tool(
    name="submit_asset_analysis",
    description=(
        "Submit your completed per-asset analysis decision. "
        "Call this ONCE per asset after you have reviewed all relevant data. "
        "IMPORTANT RULES:\n"
        "- If decision is 'buy' or 'sell': entry_condition, stop_loss, take_profit, confluence_score, priced_in_score, invalidation_price, AND invalidation_direction ('above' or 'below') are REQUIRED. R:R must be >= 1.3.\n"
        "- confluence_factors: only use exact active IDs: 'fundamental_bias', 'dxy_confirms', 'd1_trend', 'rsi_neutral', 'near_fvg', 'near_order_block', 'in_ote_zone', 'near_sr_zone', 'cot_aligned', 'vix_ok', 'liquidity_sweep_confirmed', 'session_prime', 'microstructure_ok', 'historical_pattern_consensus'.\n"
        "- If SSVP warning or macro divergence active: rationale MUST explicitly state 'I trust price action because...' or 'I trust the brief because...'.\n"
        "- If specialists disagree on direction: 'specialist_adjudication' is REQUIRED.\n"
        "- If decision is 'wait': reevaluation_trigger is required (auto-defaults to 4h time review if omitted).\n"
        "- If decision is 'avoid': only rationale is required.\n"
        "The backend will validate these rules and reject incomplete submissions."
    ),
    properties=_asset_analysis_schema["properties"],
    required=_asset_analysis_schema.get("required", []),
)


# =============================================================================
# Telegram / Chat-Mode Tools (read)
# =============================================================================

GET_ASSET_ANALYSIS = _tool(
    name="get_asset_analysis",
    description="Fetch the most recent analysis decision for a specific asset or all assets.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: specific symbol (e.g. 'XAUUSD'). Leave empty to get all assets.",
        },
        "limit": {"type": "integer", "description": "Max number of analyses to return. Default: 5."},
    },
    required=[],
)

GET_ACCOUNT_INFO = _tool(
    name="get_account_info",
    description="Fetch current account information: balance, equity, margin, free margin, and floating PnL (for live MT5 and/or simulated paper account).",
    properties={
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Account mode to inspect: 'live' for MT5 account, 'paper' for simulated paper trading portfolio ($10k baseline), 'all' for both. Default: 'all'.",
        },
    },
    required=[],
)

GET_OPEN_POSITIONS = _tool(
    name="get_open_positions",
    description="Fetch currently open trading positions (paper trades and/or live MT5 positions) with real-time floating PnL.",
    properties={
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Filter by mode: 'paper' for paper trading simulation, 'live' for MT5 live positions, 'all' for both. Default: 'all'.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'XAUUSD'). Leave empty for all open positions.",
        },
    },
    required=[],
)

GET_PENDING_ORDERS = _tool(
    name="get_pending_orders",
    description="Fetch active pending limit/stop orders from MT5 broker terminal with tickets, order types, prices, SL/TP, and volume.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'EURUSD', 'XAUUSD'). Leave empty for all pending orders.",
        },
    },
    required=[],
)

GET_PORTFOLIO_EXPOSURE = _tool(
    name="get_portfolio_exposure",
    description="Fetch portfolio-wide exposure metrics: gross/net lots, long vs short distribution, per-symbol breakdown, and aggregate unrealized PnL.",
    properties={
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Filter by trading mode: 'paper', 'live', or 'all'. Default: 'all'.",
        },
    },
    required=[],
)

GET_SWAP_RATES = _tool(
    name="get_swap_rates",
    description="Fetch overnight rollover swap rates (long and short) for trading symbols, including Wednesday 3x rollover info.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: trading symbol (e.g. 'XAUUSD', 'EURUSD'). If omitted, returns all tracked symbol swap rates.",
        },
    },
    required=[],
)

RUN_MONTE_CARLO_SIMULATION = _tool(
    name="run_monte_carlo_simulation",
    description="Run institutional Monte Carlo simulation (bootstrap / permutation) on closed trade returns to calculate VaR 95% Drawdown, Probability of Ruin, and final equity distributions.",
    properties={
        "num_simulations": {
            "type": "integer",
            "description": "Number of simulation iterations (default: 1000).",
        },
        "mode": {
            "type": "string",
            "enum": ["permutation", "bootstrap", "block_bootstrap"],
            "description": "Simulation mode (default: 'permutation').",
        },
        "initial_equity": {
            "type": "number",
            "description": "Initial account equity for simulation baseline (default: 10000.0).",
        },
        "symbol": {
            "type": "string",
            "description": "Optional: filter simulation trades by symbol.",
        },
    },
    required=[],
)

GET_PAPER_TRADING_PERFORMANCE = _tool(
    name="get_paper_trading_performance",
    description=(
        "Fetch comprehensive trading performance metrics and PnL statistics. "
        "Returns: total_trades, wins, losses, win_rate_pct, total_pnl, profit_factor, avg_pnl, "
        "expectancy_per_trade_R, has_positive_edge, by_symbol breakdown, and trade history."
    ),
    properties={
        "mode": {
            "type": "string",
            "enum": ["paper", "live", "all"],
            "description": "Trading performance mode: 'paper' for simulated tracker, 'live' for MT5 broker positions, or 'all'. Default: 'paper'.",
        },
        "days_back": {
            "type": "integer",
            "description": "Optional: number of days back to calculate statistics (e.g. 7 for past week, 30 for past month). Leave empty for all-time.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'EURUSD', 'XAUUSD').",
        },
    },
    required=[],
)

GET_TRADE_HISTORY = _tool(
    name="get_trade_history",
    description=(
        "Fetch history of executed trades (closed and open, paper and live). "
        "Returns list of trade records with symbol, direction, entry_price, exit_price, SL, TP, "
        "pnl_pct, exit_reason (tp_hit, sl_hit, manual), holding_hours, and timestamps."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'XAUUSD'). Leave empty for all.",
        },
        "status": {
            "type": "string",
            "enum": ["all", "open", "closed"],
            "description": "Filter by trade status. Default: 'closed'.",
        },
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Filter by mode: 'paper' for dry-run simulation, 'live' for MT5, 'all' for both. Default: 'all'.",
        },
        "limit": {
            "type": "integer",
            "description": "Max number of records to return. Default: 10, max: 50.",
        },
        "days_back": {
            "type": "integer",
            "description": "Optional: filter trades closed within last N days.",
        },
    },
    required=[],
)

GET_ACTIVE_TRIGGERS = _tool(
    name="get_active_triggers",
    description=(
        "Fetch active and pending trade triggers and re-evaluation conditions. "
        "Returns trigger_type (price_level, time, event), condition details, target symbol, "
        "current market price, and distance to trigger level."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'EURUSD'). Leave empty for all.",
        },
        "status": {
            "type": "string",
            "enum": ["pending", "triggered", "cancelled", "all"],
            "description": "Filter by trigger status. Default: 'pending'.",
        },
        "limit": {
            "type": "integer",
            "description": "Max number of triggers to return. Default: 10.",
        },
    },
    required=[],
)

GET_SYSTEM_HEALTH = _tool(
    name="get_system_health",
    description=(
        "Fetch comprehensive system health status: cycle scheduler status, last cycle run timestamp, "
        "risk circuit breaker / paused status, active scrapers health, MT5 connection status, and recent error count."
    ),
    properties={},
    required=[],
)

GET_EDGE_TRACKER_STATUS = _tool(
    name="get_edge_tracker_status",
    description=(
        "Fetch statistical edge evaluation, Z-score, confidence intervals, and win rates by confluence factor."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Period to evaluate statistical edge. Default: 30 days.",
        },
    },
    required=[],
)

GET_CALIBRATION_STATUS = _tool(
    name="get_calibration_status",
    description=(
        "Fetch active system calibration directives: news impact directives, currency confidence ceilings, "
        "SSVP CDS thresholds, and specialist (technical/macro/sentiment) trust weights."
    ),
    properties={},
    required=[],
)

GET_TOKEN_USAGE_AND_COSTS = _tool(
    name="get_token_usage_and_costs",
    description=(
        "Fetch AI token consumption and estimated API costs for today and past days across models and task roles."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Number of days back to report. Default: 1 (today).",
        },
    },
    required=[],
)

GET_TRADE_DETAILS = _tool(
    name="get_trade_details",
    description=(
        "Fetch deep trade autopsy and context for a specific trade: original analysis rationale, "
        "confluence factors, specialist debate transcript, execution data, exit outcome, and reflection."
    ),
    properties={
        "trade_id": {
            "type": "integer",
            "description": "PaperTradeRecord ID or Position ID.",
        },
        "analysis_id": {
            "type": "integer",
            "description": "AssetAnalysis ID.",
        },
        "ticket": {
            "type": "integer",
            "description": "MT5 ticket number.",
        },
    },
    required=[],
)

GET_MARKET_CORRELATIONS = _tool(
    name="get_market_correlations",
    description=(
        "Calculate recent return correlations between monitored trading pairs (e.g. EURUSD vs GBPUSD, XAUUSD vs DXY)."
    ),
    properties={
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of symbols. Default: all active watchlist symbols.",
        },
        "days_back": {
            "type": "integer",
            "description": "Lookback days for return correlation. Default: 30.",
        },
    },
    required=[],
)

GET_RECENT_ACTIVITY = _tool(
    name="get_recent_activity",
    description="Fetch recent system activity log entries (analysis cycles, trades, errors).",
    properties={
        "limit": {"type": "integer", "description": "Number of entries to return. Default: 20."},
        "category": {
            "type": "string",
            "description": "Optional: filter by category (scraping, analysis, trading, risk, telegram, system).",
        },
    },
    required=[],
)

GET_RISK_STATE = _tool(
    name="get_risk_state",
    description="Fetch current risk state: daily PnL, current drawdown, whether trading is paused, and reason.",
    properties={},
    required=[],
)

GET_CONVERSATION_HISTORY = _tool(
    name="get_conversation_history",
    description="Fetch previous Telegram conversation messages for context continuity.",
    properties={
        "limit": {"type": "integer", "description": "Number of most recent messages to fetch. Default: 20."},
    },
    required=[],
)

# =============================================================================
# Database Inspection & Administration Tools (Admin Only)
# =============================================================================

INSPECT_DATABASE_SCHEMA = _tool(
    name="inspect_database_schema",
    description=(
        "Inspect database tables and schema structure. Exclusively available to Admin. "
        "Returns list of all available tables in the database with their columns, primary keys, and types. "
        "Provide table_name to view detailed column definitions for a specific table, or omit to list all available tables."
    ),
    properties={
        "table_name": {
            "type": "string",
            "description": "Optional specific table name (e.g. 'system_config', 'positions', 'paper_trade_records', 'trade_triggers') to inspect in detail."
        }
    },
    required=[],
)

READ_DATABASE_RECORDS = _tool(
    name="read_database_records",
    description=(
        "Query records from any database table. Exclusively available to Admin. "
        "Returns formatted records with sensitive fields masked. "
        "Supports equality filtering, sorting, pagination, and column selection. Read-only operation."
    ),
    properties={
        "table_name": {
            "type": "string",
            "description": "Name of the table to query (e.g. 'system_config', 'positions', 'paper_trade_records', 'trade_triggers')."
        },
        "filters": {
            "type": "object",
            "description": "Optional key-value equality filters, e.g. {'symbol': 'EURUSD', 'status': 'open'} or {'key': 'trailing_stop'}."
        },
        "columns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of column names to retrieve. If omitted, returns all columns."
        },
        "order_by": {
            "type": "string",
            "description": "Optional column name to sort by, with optional 'asc' or 'desc', e.g. 'created_at desc' or 'id desc'."
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of records to return (default 10, max 50)."
        },
        "offset": {
            "type": "integer",
            "description": "Number of records to skip for pagination (default 0)."
        }
    },
    required=["table_name"],
)

PROPOSE_ACTION = _tool(
    name="propose_action",
    description=(
        "Propose an action that requires human confirmation before execution. "
        "This sends a Telegram message with inline Yes/Cancel buttons. "
        "Use for: closing a live/paper position, partial close and breakeven, placing orders, bulk breakeven, trailing stops, pausing/resuming trading, modifying SL/TP, cancelling pending MT5 orders, cancelling pending triggers, terminal commands, GUI automation, or proposing database mutations."
    ),
    properties={
        "action_type": {
            "type": "string",
            "enum": [
                "place_order",
                "close_position",
                "close_all_positions",
                "close_paper_trade",
                "pause_trading",
                "resume_trading",
                "modify_sl_tp",
                "modify_paper_sl_tp",
                "cancel_order",
                "cancel_trigger",
                "save_market_intelligence",
                "db_mutation",
                "bulk_breakeven",
                "secure_positions",
                "set_trailing_stop",
                "cancel_stale_pending_orders",
                "update_config",
                "update_user_preference",
                "execute_terminal_command",
                "desktop_gui_action",
                "partial_close_and_breakeven",
            ],
            "description": "Type of action to propose.",
        },
        "params": {
            "type": "object",
            "description": "Action parameters. For place_order: {symbol, direction: 'buy'|'sell', order_type: 'market'|'limit', entry_price, stop_loss, take_profit, rationale}. For close_position: {ticket, volume (optional float for partial close)}. For partial_close_and_breakeven: {ticket, volume: float, reason}. For bulk_breakeven/secure_positions: {symbol (optional), only_profit: bool}. For set_trailing_stop: {symbol (optional), trailing_pips: float}. For close_all_positions: {reason (optional)}. For close_paper_trade: {paper_trade_id or symbol, volume (optional)}. For modify_sl_tp/modify_paper_sl_tp: {ticket or paper_trade_id, sl, tp}. For cancel_order: {ticket (integer MT5 order ticket), symbol (optional)}. For cancel_trigger: {trigger_id}. For save_market_intelligence: {title, summary, intel_type, affected_symbols, directive, target_cycle}. For db_mutation: {table_name: str, operation: 'insert'|'update'|'delete', target_id: Optional[str|int], data: Optional[dict], reason: str}. For execute_terminal_command: {command: str}. For desktop_gui_action: {action: 'screenshot'|'left_click'|'type_text'|'key_press', coordinate, text, key}.",
        },
        "reason": {
            "type": "string",
            "description": "Explanation for why you are proposing this action.",
        },
    },
    required=["action_type", "params", "reason"],
)


# =============================================================================
# Priced-In Assessment Tool
# =============================================================================

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
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY')."
        },
        "timeframe": {
            "type": "string",
            "description": "Timeframe to calculate momentum (e.g. 'H4', 'D1'). Default: 'H4'."
        }
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
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD')."
        },
        "timeframe": {
            "type": "string",
            "enum": ["M15", "H1", "H4", "D1"],
            "description": "Chart timeframe. Default: 'H4'."
        },
        "candles": {
            "type": "integer",
            "description": "Number of candles to show on the chart (min: 20, max: 200). Default: 80."
        }
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

# =============================================================================
# AMIDR (Ad-Hoc Market Intelligence & Deep Research) Tools
# =============================================================================

WEB_SEARCH = _tool(
    name="web_search",
    description=(
        "Perform real-time web search for financial news, market consensus, whisper numbers, "
        "geopolitical developments, analyst expectations, and macro events. Supports Tavily with "
        "automatic multi-key rotation, Brave Search, and DuckDuckGo fallbacks."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "The search query (e.g., 'NFP whisper number consensus', 'Iran US conflict oil impact').",
        },
        "topic": {
            "type": "string",
            "enum": ["finance", "general"],
            "description": "Category domain for search. Defaults to 'finance'.",
        },
        "time_range": {
            "type": "string",
            "enum": ["day", "week", "month", "year"],
            "description": "Recency filter for search results. Defaults to 'day'.",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum search results to return (1-10). Defaults to 5.",
        },
    },
    required=["query"],
)

READ_URL = _tool(
    name="read_url",
    description=(
        "Fetch and read full webpage text content from a given URL, stripping boilerplate navigation, "
        "scripts, and ads. Ideal for deep research of breaking financial articles, earnings statements, "
        "and official central bank releases."
    ),
    properties={
        "url": {
            "type": "string",
            "description": "The HTTP/HTTPS URL of the webpage or document to read.",
        },
        "max_chars": {
            "type": "integer",
            "description": "Maximum characters to extract (defaults to 12000).",
        },
    },
    required=["url"],
)

SEARCH_ACADEMIC = _tool(
    name="search_academic",
    description=(
        "Search academic literature on arXiv for quantitative finance, econometrics, statistical arbitrage, "
        "and market microstructure research publications."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Search query for academic papers (e.g. 'order flow toxicity VPIN', 'GARCH volatility forecasting').",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of papers to retrieve (1-10, defaults to 5).",
        },
    },
    required=["query"],
)

SAVE_MARKET_INTELLIGENCE = _tool(
    name="save_market_intelligence",
    description=(
        "Save ad-hoc market intelligence, deep research findings, breaking news analysis, "
        "or operator directives to persistent database storage (user_market_intel). "
        "Injected automatically into subsequent scheduled analysis cycles."
    ),
    properties={
        "title": {
            "type": "string",
            "description": "Descriptive title of the intelligence or event.",
        },
        "summary": {
            "type": "string",
            "description": "Structured executive summary of findings, consensus numbers, or directives.",
        },
        "full_content": {
            "type": "string",
            "description": "Optional in-depth research notes, scenario matrices, or supporting quotes.",
        },
        "intel_type": {
            "type": "string",
            "enum": ["deep_research", "breaking_news", "scenario_watch", "operator_directive"],
            "description": "Type of market intelligence. Defaults to 'deep_research'.",
        },
        "affected_symbols": {
            "type": "string",
            "description": "Comma-separated symbols (e.g. 'XAUUSD,EURUSD', 'XTIUSD') or 'ALL'. Defaults to 'ALL'.",
        },
        "directive": {
            "type": "string",
            "enum": ["caution", "scenario_watch", "bias_override", "informational"],
            "description": "Operational directive for cycle analysis. Defaults to 'caution'.",
        },
        "target_cycle": {
            "type": "string",
            "enum": ["next_cycle_only", "persistent", "until_event"],
            "description": "Lifecycle rule for injection. Defaults to 'next_cycle_only'.",
        },
        "expires_in_hours": {
            "type": "integer",
            "description": "Hours until this intelligence entry expires (default 24h, max 168h).",
        },
    },
    required=["title", "summary"],
)

LIST_ACTIVE_INTELLIGENCE = _tool(
    name="list_active_intelligence",
    description=(
        "List all active, non-expired market intelligence and operator directives stored in the database."
    ),
    properties={
        "affected_symbol": {
            "type": "string",
            "description": "Optional symbol filter (e.g. 'XAUUSD'). If provided, returns entries matching 'ALL' or this symbol.",
        },
    },
    required=[],
)

ARCHIVE_MARKET_INTELLIGENCE = _tool(
    name="archive_market_intelligence",
    description=(
        "Archive or deactivate a specific market intelligence entry by its database ID "
        "so it is no longer injected into scheduled analysis cycles."
    ),
    properties={
        "intel_id": {
            "type": "integer",
            "description": "The database ID of the market intelligence record to archive.",
        },
        "reason": {
            "type": "string",
            "description": "Optional reason for archiving (e.g., 'event passed', 'operator cancelled').",
        },
    },
    required=["intel_id"],
)

# =============================================================================
# Tool Sets — group tools by context
# =============================================================================

# Stage 1 tools
STAGE1_TOOLS: list[dict] = [
    GET_ECONOMIC_CALENDAR,
    GET_INTEREST_RATES,
    GET_TREASURY_YIELDS,
    GET_BOND_YIELD_SPREADS,
    GET_FEDWATCH_PROBABILITIES,
    GET_CENTRAL_BANK_EXPECTATIONS,
    GET_NEWS_DIGEST,
    GET_NEWS_ITEMS,          # Fallback when digest unavailable
    GET_VIX,
    GET_DXY,
    GET_FEAR_GREED,
    GET_EIA_OIL_INVENTORY,
    GET_MARKET_SESSION,
    GET_SURPRISE_SUMMARY,
    GET_PRECOMPUTED_COT_SIGNALS,
    GET_COT_REPORT,          # Fallback when precomputed COT unavailable
    GET_ECONOMIC_SURPRISE,   # Fallback when surprise_summary unavailable
    GET_PRICE_MOMENTUM,      # Priced-In Score Method 3: run-up vs ATR
    GET_FUNDING_RATE,        # BTC sentiment indicator (also useful for macro)
    WEB_SEARCH,
    SAVE_MARKET_INTELLIGENCE,
    LIST_ACTIVE_INTELLIGENCE,
    ARCHIVE_MARKET_INTELLIGENCE,
    SUBMIT_FUNDAMENTAL_BRIEF,
    INSPECT_ECONOMIC_REPORT,
    DIFF_CENTRAL_BANK_DOCUMENTS,
    GET_MACRO_CROSS_REPORT_SYNTHESIS,
    GET_G10_MACRO_DIVERGENCE,
    GET_FED_NET_LIQUIDITY_AND_STRESS,
    GET_TREASURY_AUCTION_RESULTS,
]

STAGE1_TOOLS_WEEKEND_BTC: list[dict] = [
    GET_VIX,
    GET_FEAR_GREED,
    GET_FEDWATCH_PROBABILITIES,
    GET_NEWS_DIGEST,
    GET_NEWS_ITEMS,
    GET_DXY,
    GET_FUNDING_RATE,
    GET_PRICE_MOMENTUM,
    SUBMIT_FUNDAMENTAL_BRIEF,
]


GET_RETAIL_SENTIMENT = _tool(
    name="get_retail_sentiment",
    description=(
        "Get retail trader positioning data from Binance Futures (Long/Short ratio). "
        "Returns the percentage of retail long vs short positions for BTC and ETH. "
        "Contrarian signal: if retail is heavily long, smart money is often short -> bearish signal. "
        "Useful proxy for overall risk appetite."
    ),
    properties={},
    required=[],
)

GET_FOREX_SENTIMENT = _tool(
    name="get_forex_sentiment",
    description=(
        "Get retail trader positioning data from MyFxBook for major forex pairs and gold. "
        "Returns the percentage of retail long vs short positions. "
        "Contrarian signal: if retail is heavily long (>70%), smart money is often short -> bearish signal. "
        "Useful for EURUSD, GBPUSD, USDJPY, XAUUSD."
    ),
    properties={},
    required=[],
)

GET_FXSSI_SENTIMENT = _tool(
    name="get_fxssi_sentiment",
    description=(
        "Get retail trader positioning data from FXSSI for forex, metals, and energy. "
        "Includes data for XTIUSD (WTI Crude Oil), XAUUSD, EURUSD, GBPUSD, USDJPY. "
        "Use this as the primary sentiment source for XTIUSD."
    ),
    properties={},
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
            "description": "List of symbols (e.g. ['EURUSD', 'XAUUSD']). Also accepts single 'symbol' parameter."
        },
        "symbol": {
            "type": "string",
            "description": "Single symbol shorthand (e.g. 'XAUUSD'). Use this OR 'symbols', not both."
        },
        "timeframe": {
            "type": "string",
            "description": "Timeframe to check (e.g. 'D1', 'H4'). Default is 'D1'."
        }
    },
    required=[]  # accepts either 'symbol' or 'symbols'
)

GET_DAILY_RANGE_CONTEXT = _tool(
    name="get_daily_range_context",
    description=(
        "Get Average Daily Range (ADR) context for the intraday strategy. "
        "Returns the required TP band (50-80% of ADR) and max SL (35% of ADR). "
        "Use this to find a mathematically sound structural target. "
        "If today's range is already >85% of ADR, it will warn you to wait."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."}
    },
    required=["symbol"],
)

GET_OPTIMAL_INTRADAY_LEVELS = _tool(name='get_optimal_intraday_levels', description=(
    "Computes the best structurally-validated Stop Loss and Take Profit candidates for a "
    "proposed trade, constrained to the intraday ADR target band (50-80% ADR for TP, <=35% "
    "ADR for SL, dynamically scaled by current volatility regime). Scans Order Blocks, FVGs, "
    "S/R zones, liquidity pools, and swing points for real structural levels inside the "
    "mathematically-valid band, ranked by composite score. MANDATORY: call this AFTER "
    "determining direction and entry price, BEFORE finalizing stop_loss/take_profit in "
    "submit_asset_analysis. take_profit MUST be near a top candidate or submission is rejected."
), properties={
    'symbol': {'type': 'string', 'description': 'Trading symbol.'},
    'direction': {'type': 'string', 'enum': ['buy', 'sell'], 'description': 'Proposed trade direction.'},
    'entry_price': {'type': 'number', 'description': 'Candidate entry price.'}
}, required=['symbol', 'direction', 'entry_price'])

# Stage 2 tools
GET_STRUCTURED_SENTIMENT = {
    "name": "get_structured_sentiment",
    "description": "Mengambil sentimen teragregasi dan terstruktur dari institusional (COT), retail, dan VIX untuk sebuah aset.",
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Contoh: EURUSD"
            }
        },
        "required": ["symbol"]
    }
}

GET_LIQUIDITY_SWEEP_CONTEXT = _tool(name='get_liquidity_sweep_context',
    description="Detects an Asian-session (00:00-08:00 UTC) liquidity sweep (wick beyond session high/low, closes back inside) confirmed by a post-sweep ChoCH/BOS, Order Block, or FVG. Only use 'liquidity_sweep_confirmed' in confluence_factors if structure_confirmed=True AND valid_for_direction matches your decision — verified server-side.",
    properties={'symbol': {'type': 'string'}}, required=['symbol'])

GET_MACRO_BIAS_SCORE = _tool(name='get_macro_bias_score',
    description="Deterministic macro pressure score (10Y yield momentum + policy rate proxy, NOT true real yield — see output for caveat). Informational; a hard gate re-validates it against your actual decision at submission and REJECTS buy/sell that strongly contradicts it.",
    properties={'symbol': {'type': 'string'}}, required=['symbol'])

GET_VOLUME_PROFILE_CONTEXT = _tool(name='get_volume_profile_context',
    description='Session-anchored VWAP + 30-day tick-volume profile (POC/VAH/VAL) classifying market as balanced (mean-reverting) or imbalanced (trending). FX tick-volume is a broker activity proxy, not literal traded size.',
    properties={'symbol': {'type': 'string'}}, required=['symbol'])

GET_VOLATILITY_REGIME = _tool(name='get_volatility_regime',
    description='Analyze market volatility regime, expanding or contracting volatility width (Bollinger-width percentile + Donchian breakout check). chop_block=True blocks new buy/sell entries mechanically unless a breakout is confirmed.',
    properties={'symbol': {'type': 'string'}, 'timeframe': {'type': 'string', 'enum': ['H1', 'H4', 'D1']}},
    required=['symbol'])

UPDATE_SCRATCHPAD = _tool(
    name="update_scratchpad",
    description=(
        "Updates active working scratchpad with verified calculation anchors. "
        "Use this to record H4 ATR, ADR bounds, structural SL level, target TP, invalidation, "
        "and confirmed confluences. Preserved across all compaction turns."
    ),
    properties={
        "bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"], "description": "Dominant directional bias"},
        "h4_atr": {"type": "number", "description": "Verified H4 ATR 14 value"},
        "daily_adr": {"type": "number", "description": "Verified 5-day Average Daily Range (ADR)"},
        "invalidation_price": {"type": "number", "description": "Price level that invalidates the trade thesis"},
        "entry_zone": {
            "type": "object",
            "properties": {
                "low": {"type": "number"},
                "high": {"type": "number"},
                "type": {"type": "string"}
            }
        },
        "structural_sl": {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "basis": {"type": "string"}
            }
        },
        "target_tp": {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "basis": {"type": "string"}
            }
        },
        "rr_ratio": {"type": "number", "description": "Projected Reward-to-Risk ratio (must be >= 1.30)"},
        "confluence_score": {"type": "number", "description": "Composite confluence score out of 14"},
        "verified_confluences": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of confirmed confluence tags"
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short analytical bullet points"
        }
    },
    required=[]
)

READ_SCRATCHPAD = _tool(
    name="read_scratchpad",
    description="Reads current working scratchpad state and recorded analytical anchors.",
    properties={},
    required=[]
)

CALCULATE_POSITION_SIZE = _tool(
    name="calculate_position_size",
    description=(
        "Deterministic position sizing calculator. Given symbol, entry, stop_loss, direction, and risk percentage, "
        "calculates verified mathematical lot sizing, risk in USD, and pip distance based on Stop Loss. "
        "MANDATORY: LLM must use this tool and NOT calculate lot sizes manually."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'EURUSD', 'XAUUSD')"},
        "entry_price": {"type": "number", "description": "Proposed entry price"},
        "stop_loss": {"type": "number", "description": "Proposed stop loss price"},
        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Trade direction (optional)"},
        "risk_pct": {"type": "number", "description": "Account risk percentage (default: 1.0%)"},
        "account_equity": {"type": "number", "description": "Custom account equity / capital in USD (optional, defaults to live broker equity or paper balance)"}
    },
    required=["symbol", "entry_price", "stop_loss"]
)

TRANSITION_PHASE = _tool(
    name="transition_analysis_phase",
    description=(
        "Transitions agent execution to the next analytical phase (Phase 1: Recon -> "
        "Phase 2: Structure & Confluence -> Phase 3: Sizing & Submission)."
    ),
    properties={
        "target_phase": {
            "type": "integer",
            "enum": [1, 2, 3],
            "description": "Target phase number to unlock corresponding tools"
        },
        "rationale": {"type": "string", "description": "Reason for advancing phase"}
    },
    required=["target_phase"]
)

GET_TIMESFM_FORECAST = _tool(
    name="get_timesfm_forecast",
    description="Ambil proyeksi harga probabilistik (kuantil 10%, 50%, 90%) menggunakan Google TimesFM 3.0 foundation model.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. XAUUSD, EURUSD)"},
        "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"], "default": "H1", "description": "Timeframe candle untuk forecasting"},
        "horizon_steps": {"type": "integer", "default": 24, "description": "Jumlah candle proyeksi ke depan"}
    },
    required=["symbol"],
)

STAGE2_TOOLS: list[dict] = [
    GET_TIMESFM_FORECAST,
    GET_MARKET_SESSION,
    GET_MARKET_REGIME,
    GET_MULTI_TIMEFRAME_SUMMARY,
    GET_BOND_YIELD_SPREADS,
    GET_CENTRAL_BANK_EXPECTATIONS,
    GET_LIQUIDITY_SWEEP_CONTEXT,
    GET_MACRO_BIAS_SCORE,
    GET_VOLUME_PROFILE_CONTEXT,
    GET_VOLATILITY_REGIME,
    GET_FUNDAMENTAL_BRIEF,
    GET_NEWS_ITEMS,
    GET_ECONOMIC_CALENDAR,
    GET_PRICE_HISTORY,
    GET_TECHNICAL_INDICATORS,
    GET_ATR,
    GET_DAILY_RANGE_CONTEXT,
    GET_OPTIMAL_INTRADAY_LEVELS,
    GET_DXY,
    GET_SWING_POINTS,
    GET_STRUCTURE_BREAKS,
    GET_FIBONACCI_LEVELS,
    GET_SMC_ZONES,
    GET_SR_ZONES,
    GET_LIQUIDITY_ZONES,
    GET_FVG_ZONES,
    GET_ORDER_BLOCKS,
    GET_PRECOMPUTED_COT_SIGNALS,
    GET_COT_REPORT,
    GET_VIX,
    GET_EIA_OIL_INVENTORY,
    GET_FEAR_GREED,
    GET_FUNDING_RATE,
    GET_RETAIL_SENTIMENT,
    GET_FOREX_SENTIMENT,
    GET_FXSSI_SENTIMENT,
    GET_PRICE_MOMENTUM,
    GET_OPEN_POSITIONS,
    GET_RISK_STATE,
    GET_STRUCTURED_SENTIMENT,
    GET_SPREAD_SNAPSHOT,
    CALCULATE_POSITION_SIZE,
    UPDATE_SCRATCHPAD,
    READ_SCRATCHPAD,
    TRANSITION_PHASE,
    WEB_SEARCH,
    READ_URL,
    SEARCH_ACADEMIC,
    SUBMIT_ASSET_ANALYSIS,
]

# =============================================================================
# Composite Tools (ACI-Style Batch Tools)
# =============================================================================

GET_MARKET_CONTEXT = _tool(
    name="get_market_context",
    description=(
        "Composite macro context tool — returns market_session, DXY, VIX, "
        "fundamental_brief, open_positions, and risk_state in a single unified call. "
        "Use this FIRST to fetch all environment context at once."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading symbol for brief and position context."
        },
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
        "symbol": {
            "type": "string",
            "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD')."
        },
        "timeframes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Timeframes to analyze. Default: ['D1', 'H4']."
        }
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
        "symbol": {
            "type": "string",
            "description": "Trading symbol."
        },
        "direction": {
            "type": "string",
            "enum": ["buy", "sell"],
            "description": "Optional: trade direction for optimal level optimization."
        },
        "entry_price": {
            "type": "number",
            "description": "Optional: planned entry price for structural level mapping."
        }
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
        "symbol": {
            "type": "string",
            "description": "Trading symbol."
        },
        "cot_code": {
            "type": "string",
            "description": "Optional COT market code (e.g. '088691' for Gold)."
        }
    },
    required=["symbol"],
)

# Deterministic Position Sizing Tool (CALCULATE_POSITION_SIZE is defined above)


# Consolidated Stage 2 Essential Tool Suite (Core Tools: Pinned for 100% KV-Cache hit rate & Zero bloat)
STAGE2_ESSENTIAL_TOOLS: list[dict] = [
    SUBMIT_ASSET_ANALYSIS,
    CALCULATE_POSITION_SIZE,
    UPDATE_SCRATCHPAD,
    READ_SCRATCHPAD,
    GET_NEWS_ITEMS,
    GET_ECONOMIC_CALENDAR,
    GET_OPTIMAL_INTRADAY_LEVELS,
    GET_SPREAD_SNAPSHOT,
]

# SOTA Frozen Tool Suite (Deterministic Tools for 100% KV-Cache prefix hit rate across all symbols and turns)
STAGE2_FROZEN_TOOLS: list[dict] = [
    SUBMIT_ASSET_ANALYSIS,
    CALCULATE_POSITION_SIZE,
    UPDATE_SCRATCHPAD,
    READ_SCRATCHPAD,
    GET_OPTIMAL_INTRADAY_LEVELS,
    GET_SPREAD_SNAPSHOT,
    GET_NEWS_ITEMS,
    GET_ECONOMIC_CALENDAR,
    GET_PRICE_DATA,
    GET_TECHNICAL_ANALYSIS,
    GET_INSTITUTIONAL_DATA,
    GET_EIA_OIL_INVENTORY,
    SCAN_PATTERN_SIMILARITY,
]

STAGE2_EXPANDED_TOOLS: list[dict] = STAGE2_FROZEN_TOOLS

# Stage 2 Prescreen tools (lightweight subset to filter non-setups before full debate)
STAGE2_PRESCREEN_TOOLS: list[dict] = [
    GET_PRICE_HISTORY,
    GET_TECHNICAL_INDICATORS,
    GET_MULTI_TIMEFRAME_SUMMARY,
    GET_ATR,
    GET_SMC_ZONES,
    GET_FUNDAMENTAL_BRIEF,
    SUBMIT_ASSET_ANALYSIS,
]

# Telegram / chat-mode tools (broad read access + propose_action)
TELEGRAM_TOOLS: list[dict] = [
    # === DATA PASAR & MAKRO ===
    GET_MARKET_SESSION,
    GET_FUNDAMENTAL_BRIEF,
    GET_ECONOMIC_CALENDAR,
    GET_WEEKLY_MACRO_SUMMARY,
    GET_INTEREST_RATES,
    GET_TREASURY_YIELDS,
    GET_FEDWATCH_PROBABILITIES,
    GET_CENTRAL_BANK_EXPECTATIONS,
    GET_EIA_OIL_INVENTORY,
    GET_NEWS_ITEMS,
    GET_NEWS_DIGEST,
    GET_VIX,
    GET_COT_REPORT,
    GET_BOND_YIELD_SPREADS,
    GET_SPREAD_SNAPSHOT,
    
    # === REVIEW TEKNIKAL & SMC ===
    GET_CHART,
    GET_PRICE_HISTORY,
    GET_TECHNICAL_INDICATORS,
    GET_MULTI_TIMEFRAME_SUMMARY,
    GET_ATR,
    GET_SWING_POINTS,
    GET_STRUCTURE_BREAKS,
    GET_SMC_ZONES,
    GET_FVG_ZONES,
    GET_ORDER_BLOCKS,
    GET_SR_ZONES,
    GET_LIQUIDITY_ZONES,
    GET_VOLUME_PROFILE_CONTEXT,
    GET_FIBONACCI_LEVELS,
    GET_DXY,
    GET_PRICE_MOMENTUM,
    GET_DAILY_RANGE_CONTEXT,
    GET_OPTIMAL_INTRADAY_LEVELS,
    GET_MARKET_REGIME,
    GET_VOLATILITY_REGIME,
    
    # === SENTIMENT ===
    GET_FEAR_GREED,
    GET_FUNDING_RATE,
    GET_RETAIL_SENTIMENT,
    GET_FOREX_SENTIMENT,
    GET_FXSSI_SENTIMENT,
    GET_STRUCTURED_SENTIMENT,
    
    # === PORTFOLIO, PAPER TRADING & STATS ===
    GET_PAPER_TRADING_PERFORMANCE,
    GET_TRADE_HISTORY,
    GET_ASSET_ANALYSIS,
    GET_ACCOUNT_INFO,
    GET_OPEN_POSITIONS,
    GET_PENDING_ORDERS,
    GET_PORTFOLIO_EXPOSURE,
    GET_SWAP_RATES,
    GET_ACTIVE_TRIGGERS,
    GET_TRADE_DETAILS,
    
    # === ANALISIS KUANTITATIF & KALIBRASI ===
    GET_TIMESFM_FORECAST,
    GET_EDGE_TRACKER_STATUS,
    GET_CALIBRATION_STATUS,
    GET_MARKET_CORRELATIONS,
    RUN_MONTE_CARLO_SIMULATION,
    
    # === SYSTEM HEALTH, AUDIT & RISK ===
    GET_SYSTEM_HEALTH,
    GET_TOKEN_USAGE_AND_COSTS,
    GET_RECENT_ACTIVITY,
    GET_RISK_STATE,
    GET_CONVERSATION_HISTORY,

    # === AMIDR DEEP RESEARCH & OPERATOR INTEL ===
    WEB_SEARCH,
    READ_URL,
    SEARCH_ACADEMIC,
    SAVE_MARKET_INTELLIGENCE,
    LIST_ACTIVE_INTELLIGENCE,
    ARCHIVE_MARKET_INTELLIGENCE,
    
    # === DATABASE INSPECTION & ADMIN OPERATIONS ===
    INSPECT_DATABASE_SCHEMA,
    READ_DATABASE_RECORDS,

    # === SIZING & SMC CONTEXT ===
    CALCULATE_POSITION_SIZE,
    GET_LIQUIDITY_SWEEP_CONTEXT,
    SCAN_PATTERN_SIMILARITY,

    # === EKSEKUSI ===
    PROPOSE_ACTION,
]

CALCULATE_MARGIN = _tool(
    name="calculate_margin",
    description=(
        "Calculates exact broker margin requirement in USD for a specified lot size and symbol. "
        "Accounts for leverage, broker contract size, and current market price."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'XAUUSD', 'EURUSD')"},
        "lot_size": {"type": "number", "description": "Lot size volume (e.g. 0.5, 1.0)"},
        "action": {"type": "string", "enum": ["buy", "sell"], "description": "Trade action (default 'buy')"},
        "price": {"type": "number", "description": "Current price (optional)"}
    },
    required=["symbol", "lot_size"]
)
TELEGRAM_TOOLS.append(CALCULATE_MARGIN)

CREATE_PRICE_ALERT = _tool(
    name="create_price_alert",
    description=(
        "Creates an ad-hoc price alert trigger that notifies the operator via Telegram when market price "
        "crosses a specific level (break above / break below)."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'EURUSD', 'XAUUSD')"},
        "price_level": {"type": "number", "description": "Price level target to trigger alert"},
        "condition": {"type": "string", "enum": ["above", "below"], "description": "Trigger when price goes above or below level"},
        "note": {"type": "string", "description": "Optional memo or description for the alert"}
    },
    required=["symbol", "price_level", "condition"]
)
TELEGRAM_TOOLS.append(CREATE_PRICE_ALERT)

# Deterministic Ground-Truth Market Snapshot (H-7 / Anti-Hallucination)
GET_VERIFIED_MARKET_SNAPSHOT = _tool(
    name="get_verified_market_snapshot",
    description=(
        "Deterministic ground-truth market snapshot. Computes latest verified OHLCV bar, "
        "RSI, MACD, ATR, EMA (20/50/200), and key S/R levels directly from verified data. "
        "THIS IS SACRED GROUND TRUTH: LLM must treat these numbers as exact and never hallucinate price levels."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Trading instrument symbol (e.g. 'EURUSD', 'XAUUSD', 'BTCUSD')."
        }
    },
    required=["symbol"],
)

STAGE2_ESSENTIAL_TOOLS.append(GET_VERIFIED_MARKET_SNAPSHOT)
STAGE2_FROZEN_TOOLS.append(GET_VERIFIED_MARKET_SNAPSHOT)
STAGE2_TOOLS.append(GET_VERIFIED_MARKET_SNAPSHOT)
TELEGRAM_TOOLS.append(GET_VERIFIED_MARKET_SNAPSHOT)

# Current Market Quote Tool (Live tick / current price)
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
            "description": "Trading instrument symbol (e.g. 'EURUSD', 'XAUUSD', 'GBPUSD', 'BTCUSD')."
        }
    },
    required=["symbol"],
)

STAGE1_TOOLS.append(GET_MARKET_QUOTE)
STAGE2_ESSENTIAL_TOOLS.append(GET_MARKET_QUOTE)
STAGE2_FROZEN_TOOLS.append(GET_MARKET_QUOTE)
STAGE2_TOOLS.append(GET_MARKET_QUOTE)
STAGE2_PRESCREEN_TOOLS.append(GET_MARKET_QUOTE)
TELEGRAM_TOOLS.append(GET_MARKET_QUOTE)

EXECUTE_ANALYSIS_CODE = _tool(
    name="execute_analysis_code",
    description=(
        "Execute a Python script to perform batch data operations efficiently. "
        "Use when you need to call multiple tools with similar parameters (e.g., "
        "fetching price history for 8 pairs, or computing indicators across timeframes). "
        "The script has access to a 'tools' object where you can call any registered tool "
        "as tools.tool_name(param=value). Print final results to stdout as JSON. "
        "This avoids multiple LLM round-trips for repetitive operations."
    ),
    properties={
        "code": {
            "type": "string",
            "description": "Python code to execute. Use tools.get_price_history(symbol='EURUSD', timeframe='H4') etc.",
        },
    },
    required=["code"],
)

RETRIEVE_SPILLED_CONTEXT = _tool(
    name="retrieve_spilled_context",
    description=(
        "Retrieve spilled tool observations or large context blobs from PostgreSQL or disk caches by blob_id. "
        "Supports pagination via offset and max_chars."
    ),
    properties={
        "blob_id": {
            "type": "string",
            "description": "The blob pointer or identifier (e.g. 'spill_1234abcd' or 'db://spill/spill_1234abcd').",
        },
        "offset": {
            "type": "integer",
            "description": "Starting character offset for pagination (default 0).",
        },
        "max_chars": {
            "type": "integer",
            "description": "Maximum characters to retrieve (default 4000, max 15000).",
        },
    },
    required=["blob_id"],
)

STAGE2_TOOLS.append(RETRIEVE_SPILLED_CONTEXT)
if RETRIEVE_SPILLED_CONTEXT not in STAGE2_ESSENTIAL_TOOLS:
    STAGE2_ESSENTIAL_TOOLS.append(RETRIEVE_SPILLED_CONTEXT)

DELEGATE_SPECIALIST_ANALYSIS = _tool(
    name="delegate_specialist_analysis",
    description=(
        "Delegate deep specialized analysis to an isolated subagent. "
        "The specialist runs with isolated context, avoiding parent history pollution, "
        "and returns a structured analytical summary. "
        "Roles: 'macro_specialist', 'technical_specialist', 'sentiment_specialist', 'risk_specialist'."
    ),
    properties={
        "specialist_role": {
            "type": "string",
            "enum": ["macro_specialist", "technical_specialist", "sentiment_specialist", "risk_specialist"],
            "description": "Specialist subagent role to execute.",
        },
        "task_prompt": {
            "type": "string",
            "description": "Concrete prompt detailing the specialized task to analyze.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional trading instrument symbol (e.g. 'EURUSD', 'XAUUSD').",
        },
    },
    required=["specialist_role", "task_prompt"],
)

TELEGRAM_TOOLS.append(DELEGATE_SPECIALIST_ANALYSIS)
if DELEGATE_SPECIALIST_ANALYSIS not in STAGE1_TOOLS:
    STAGE1_TOOLS.append(DELEGATE_SPECIALIST_ANALYSIS)
if DELEGATE_SPECIALIST_ANALYSIS not in STAGE2_ESSENTIAL_TOOLS:
    STAGE2_ESSENTIAL_TOOLS.append(DELEGATE_SPECIALIST_ANALYSIS)

SKILLS_LIST_TOOL = _tool(
    name="skills_list",
    description=(
        "List all available institutional trading playbooks, analytical frameworks, and tactical skills. "
        "Returns skill names, categories, and concise capability summaries. "
        "Use this to discover specialized frameworks without prompt token bloat."
    ),
    properties={},
    required=[],
)

SKILL_VIEW_TOOL = _tool(
    name="skill_view",
    description=(
        "Retrieve and view the full content and operational guidelines of a specific trading skill or playbook by name. "
        "Available skills include: 'central_banks_framework', 'event_probability_playbook', 'smc_ict_playbook', "
        "'macro_analysis_framework', 'market_dynamics_framework', 'adjudication_framework', etc."
    ),
    properties={
        "skill_name": {
            "type": "string",
            "description": "Exact name of the skill or playbook to inspect (without .md extension).",
        }
    },
    required=["skill_name"],
)

CREATE_SKILL_TOOL = _tool(
    name="create_skill",
    description=(
        "Create, author, and register a new persistent trading skill or playbook markdown file in the system. "
        "Use when user asks to create a new skill, save an identified edge/pattern into a playbook, or distill learnings into a reusable skill."
    ),
    properties={
        "skill_name": {
            "type": "string",
            "description": "Identifier for the skill (e.g. 'gold_london_sweep_playbook', 'orderblock_reversal').",
        },
        "content": {
            "type": "string",
            "description": "Complete markdown instructions, entry/exit criteria, and rules for the skill.",
        },
        "category": {
            "type": "string",
            "description": "Category for the skill: 'trading', 'tactical', 'macro', 'technical', 'discipline'. Default: 'trading'.",
        },
        "description": {
            "type": "string",
            "description": "Short 1-sentence description or summary of the skill.",
        },
    },
    required=["skill_name", "content"],
)

TELEGRAM_TOOLS.extend([SKILLS_LIST_TOOL, SKILL_VIEW_TOOL, CREATE_SKILL_TOOL])
if SKILLS_LIST_TOOL not in STAGE1_TOOLS:
    STAGE1_TOOLS.append(SKILLS_LIST_TOOL)
if SKILL_VIEW_TOOL not in STAGE1_TOOLS:
    STAGE1_TOOLS.append(SKILL_VIEW_TOOL)
if CREATE_SKILL_TOOL not in STAGE1_TOOLS:
    STAGE1_TOOLS.append(CREATE_SKILL_TOOL)
if SKILLS_LIST_TOOL not in STAGE2_ESSENTIAL_TOOLS:
    STAGE2_ESSENTIAL_TOOLS.append(SKILLS_LIST_TOOL)
if SKILL_VIEW_TOOL not in STAGE2_ESSENTIAL_TOOLS:
    STAGE2_ESSENTIAL_TOOLS.append(SKILL_VIEW_TOOL)
if CREATE_SKILL_TOOL not in STAGE2_ESSENTIAL_TOOLS:
    STAGE2_ESSENTIAL_TOOLS.append(CREATE_SKILL_TOOL)

RUN_TRADE_COUNTERFACTUAL = _tool(
    name="run_trade_counterfactual",
    description=(
        "Run a counterfactual replay on a specific historical trade setup or ticket to evaluate what would have happened "
        "if stop loss or take profit were wider/narrower (e.g. SL +10 pips). "
        "Use when user asks 'what if SL was wider', 'counterfactual analysis for trade #X', or post-trade what-if scenarios."
    ),
    properties={
        "trade_id": {
            "type": "integer",
            "description": "Ticket ID or Database ID of the trade/position to replay.",
        },
        "sl_pips_delta": {
            "type": "number",
            "description": "Additional pips added to Stop Loss distance (positive means wider SL, e.g. 10.0 for 10 pips wider). Default: 0.0.",
        },
        "tp_pips_delta": {
            "type": "number",
            "description": "Additional pips added to Take Profit distance (positive means wider TP, e.g. 20.0). Default: 0.0.",
        },
    },
    required=["trade_id"],
)

TELEGRAM_TOOLS.append(RUN_TRADE_COUNTERFACTUAL)

GET_DEBATE_STATISTICS = _tool(
    name="get_debate_statistics",
    description=(
        "Retrieve aggregated debate outcome metrics across historical analyses (e.g. Bull vs Bear wins in last 30 days). "
        "Use when user asks 'how many times bull won vs bear', 'debate statistics', or outcome ratios."
    ),
    properties={
        "days": {
            "type": "integer",
            "description": "Number of days back to aggregate debate outcomes (default: 30).",
        },
    },
    required=[],
)

GET_REJECTION_HISTORY = _tool(
    name="get_rejection_history",
    description=(
        "Retrieve historical orders and trade proposals that were blocked or rejected by RiskGate or preflight checks. "
        "Use when user asks for rejected orders history, why trades were blocked in the past, or risk veto logs."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional symbol filter (e.g. 'USDJPY', 'XAUUSD').",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum records to return (default: 20).",
        },
    },
    required=[],
)

GET_MARKET_CHRONICLE = _tool(
    name="get_market_chronicle",
    description=(
        "Retrieve market chronicle entries and structural macro milestones (e.g. historical central bank shifts, tariffs, geopolitical events) "
        "by month/year or category. Use when user asks for 'trading chronicle', 'market chronicle for September', or long-term macro timeline."
    ),
    properties={
        "month": {
            "type": "string",
            "description": "Optional month name or number (e.g. 'September', '9', 'Januari').",
        },
        "year": {
            "type": "integer",
            "description": "Optional calendar year (e.g. 2026).",
        },
        "category": {
            "type": "string",
            "description": "Optional category filter: 'policy_change', 'geopolitical', 'data_shock', 'regime_shift', 'institutional'.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of chronicles to retrieve (default: 20).",
        },
    },
    required=[],
)

TELEGRAM_TOOLS.extend([GET_DEBATE_STATISTICS, GET_REJECTION_HISTORY, GET_MARKET_CHRONICLE])

SEARCH_HISTORICAL_MEMORIES = _tool(
    name="search_historical_memories",
    description=(
        "Search past trading decisions, post-trade reflections, lessons learned, and precedent market scenarios. "
        "Use this tool when answering questions about previous trades, past win/loss outcomes, lessons from specific setups, "
        "or how the system handled similar market conditions in the past."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Keywords or semantic concepts to search across historical reflections and decisions.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional symbol (e.g. 'EURUSD', 'XAUUSD') to narrow precedent search.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of precedent records to retrieve (default: 5).",
        },
    },
    required=["query"],
)

TELEGRAM_TOOLS.append(SEARCH_HISTORICAL_MEMORIES)

MANAGE_CRON = _tool(
    name="manage_cron",
    description=(
        "Schedules, lists, or removes dynamic recurring cron tasks or reminders. "
        "Use when the operator asks to schedule a recurring scan, report, or reminder."
    ),
    properties={
        "action": {"type": "string", "enum": ["add", "list", "remove", "clear"], "description": "Action to perform"},
        "name": {"type": "string", "description": "Unique identifier name for the cron job."},
        "cron_expression": {"type": "string", "description": "Standard 5-part cron expression (e.g. '0 9 * * 1-5', '*/30 * * * *')."},
        "instruction": {"type": "string", "description": "The command, prompt, or instruction to execute on schedule."},
        "description": {"type": "string", "description": "Optional memo/description."},
    },
    required=["action"],
)
TELEGRAM_TOOLS.append(MANAGE_CRON)

QUERY_SIGNAL_PERFORMANCE = _tool(
    name="query_signal_performance",
    description=(
        "Query trade signals joined with execution outcomes with flexible filters. "
        "Allows finding signals by confidence threshold (e.g. confidence > 0.8), outcome ('win'/'loss'), symbol, and time range."
    ),
    properties={
        "min_confidence": {"type": "number", "description": "Minimum AI signal confidence (0.0 - 1.0). Default: 0.0."},
        "max_confidence": {"type": "number", "description": "Maximum AI signal confidence. Default: 1.0."},
        "outcome": {"type": "string", "enum": ["all", "win", "loss"], "description": "Filter by outcome: 'win' (positive pnl), 'loss' (negative pnl), or 'all'."},
        "symbol": {"type": "string", "description": "Optional symbol filter (e.g. 'EURUSD')."},
        "days_back": {"type": "integer", "description": "Lookback window in days (default: 30)."},
        "limit": {"type": "integer", "description": "Maximum records to return (default: 20)."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(QUERY_SIGNAL_PERFORMANCE)

GET_LATEST_RISK_VERDICT = _tool(
    name="get_latest_risk_verdict",
    description=(
        "Retrieve recent RiskGate trade rejection reasons, failed check criteria, and risk audit logs for a symbol or account."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD')."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(GET_LATEST_RISK_VERDICT)

EXPORT_DEBATE_TRANSCRIPTS = _tool(
    name="export_debate_transcripts",
    description=(
        "Export specialist Bull vs Bear adversarial debate theses, dissent arguments, and judge verdicts to JSON."
    ),
    properties={
        "symbol": {"type": "string", "description": "Optional symbol to filter debate records."},
        "days_back": {"type": "integer", "description": "Lookback days for debates (default: 30)."},
        "limit": {"type": "integer", "description": "Maximum debate records to export (default: 100)."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(EXPORT_DEBATE_TRANSCRIPTS)

TRIGGER_LEARNING_CYCLE = _tool(
    name="trigger_learning_cycle",
    description=(
        "Trigger the system self-reflection and learning loop: reviews recent closed trades, identifies error patterns, "
        "synthesizes negative constraints, and updates institutional playbooks."
    ),
    properties={
        "days_back": {"type": "integer", "description": "Lookback days for reflection (default: 7)."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(TRIGGER_LEARNING_CYCLE)

RUN_SYSTEM_DOCTOR_CHECK = _tool(
    name="run_system_doctor_check",
    description=(
        "Run comprehensive system doctor diagnostic check verifying directories, API keys, MT5 terminal bridge, database tables, and scrapers."
    ),
    properties={},
    required=[],
)
TELEGRAM_TOOLS.append(RUN_SYSTEM_DOCTOR_CHECK)

SET_TRAILING_STOP = _tool(
    name="set_trailing_stop",
    description=(
        "Set or update trailing stop and breakeven configurations for active positions (either by ticket, symbol, or all profitable positions)."
    ),
    properties={
        "ticket": {"type": "integer", "description": "Optional MT5 ticket number for specific position."},
        "symbol": {"type": "string", "description": "Optional symbol filter (e.g. 'EURUSD')."},
        "trailing_pips": {"type": "number", "description": "Static trailing stop distance in pips (e.g. 20.0)."},
        "breakeven_pips": {"type": "number", "description": "Profit threshold in pips to move SL to breakeven (e.g. 15.0)."},
        "trail_atr_multiple": {"type": "number", "description": "Dynamic ATR multiple for trailing stop (e.g. 1.5)."},
        "only_profit": {"type": "boolean", "description": "If true, applies only to currently profitable positions (default: false)."},
        "disabled": {"type": "boolean", "description": "Set true to disable trailing stop on target positions."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(SET_TRAILING_STOP)

EXPORT_HISTORICAL_DATA_CSV = _tool(
    name="export_historical_data_csv",
    description=(
        "Export historical OHLCV candle data to a CSV file on disk for external backtesting and quant research."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading pair symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "description": "Candle timeframe ('M15', 'H1', 'H4', 'D1'). Default: 'H1'."},
        "days_back": {"type": "integer", "description": "Number of days of historical data to export (default: 30)."},
        "output_filename": {"type": "string", "description": "Optional custom filename for the CSV."},
    },
    required=["symbol"],
)
TELEGRAM_TOOLS.append(EXPORT_HISTORICAL_DATA_CSV)

TRIGGER_MARKET_SCAN = _tool(
    name="trigger_market_scan",
    description=(
        "Trigger ad-hoc market opportunity scan across symbols and return top ranked trade recommendations based on current market regime and macro conditions."
    ),
    properties={
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of symbols to scan. Defaults to active asset universe.",
        },
        "force": {"type": "boolean", "description": "Force fresh scan even if cached brief exists."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(TRIGGER_MARKET_SCAN)

RUN_STRATEGY_BACKTEST = _tool(
    name="run_strategy_backtest",
    description=(
        "Run isolated point-in-time strategy backtest on historical OHLCV data. "
        "Returns: total trades, win rate %, profit factor, Sharpe ratio, Sortino ratio, max drawdown %, and sample trade list."
    ),
    properties={
        "symbol": {"type": "string", "description": "Symbol to test (e.g. 'EURUSD', 'XAUUSD', 'BTCUSD')."},
        "timeframe": {"type": "string", "description": "Timeframe ('H1', 'H4', 'M15'). Default: 'H1'."},
        "strategy": {"type": "string", "description": "Strategy name (e.g. 'smc_fvg', 'btc_donchian_breakout', 'gap_fade', 'xau_trend', 'tsm_momentum', 'tri_convergent')."},
        "days_back": {"type": "integer", "description": "Lookback historical window in days (default: 90)."},
    },
    required=["symbol"],
)
TELEGRAM_TOOLS.append(RUN_STRATEGY_BACKTEST)

GET_PNL_SUMMARY = _tool(
    name="get_pnl_summary",
    description=(
        "Retrieve aggregated profit/loss summary for real and paper trades across horizons: "
        "today, this week (Monday to now), this month, and all-time. "
        "Includes total PnL ($), trade counts, win rate %, and win/loss breakdown."
    ),
    properties={
        "horizons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of horizons to query (e.g. ['today', 'this_week', 'this_month']). Defaults to all.",
        },
    },
    required=[],
)
TELEGRAM_TOOLS.append(GET_PNL_SUMMARY)

PLOT_PRICE_CHART = _tool(
    name="plot_price_chart",
    description=(
        "Plot a high-resolution dark-theme candlestick chart with SMC overlays (Fair Value Gap boxes & Swing Pivots). "
        "Saves the resulting PNG image to disk and delivers it directly to the user's interface."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'XAUUSD', 'EURUSD')."},
        "timeframe": {"type": "string", "description": "Candle timeframe ('M5', 'M15', 'H1', 'H4', 'D1'). Default: 'H1'."},
        "candles": {"type": "integer", "description": "Number of recent candles to plot (default: 80)."},
        "overlay_smc": {"type": "boolean", "description": "Whether to render FVG boxes and swing pivot markers (default: true)."},
    },
    required=["symbol"],
)
TELEGRAM_TOOLS.append(PLOT_PRICE_CHART)

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
TELEGRAM_TOOLS.append(DETECT_CANDLESTICK_PATTERNS)

RUN_ADHOC_SYMBOL_DEBATE = _tool(
    name="run_adhoc_symbol_debate",
    description=(
        "Trigger an ad-hoc Multi-Agent Debate session (Bull Specialist vs Bear Specialist vs Investment Judge) "
        "for a specific symbol to evaluate conflicting structural, fundamental, and quantitative evidence."
    ),
    properties={
        "symbol": {"type": "string", "description": "The asset symbol to debate (e.g. 'XAUUSD', 'EURUSD', 'BTCUSD')."},
    },
    required=["symbol"],
)
TELEGRAM_TOOLS.append(RUN_ADHOC_SYMBOL_DEBATE)

RUN_HOSTILE_STRESS_TEST = _tool(
    name="run_hostile_stress_test",
    description=(
        "Run Hostile Market Feed Wire Probes and RiskGate adversarial stress testing battery "
        "(flash crashes, spread blowouts, crossed book, stale feeds, zero-liquidity) to verify fail-closed protection."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol to probe (default: 'EURUSD')."},
    },
    required=[],
)
TELEGRAM_TOOLS.append(RUN_HOSTILE_STRESS_TEST)

RUN_ANALYTICAL_QUERY = _tool(
    name="run_analytical_query",
    description=(
        "Execute safe, parameterized analytical aggregation query on historical trade performance, "
        "regime expectancy, holding times, session win-rates, MAE/MFE distribution, and slippage. "
        "Use this for post-mortems, institutional performance auditing, and statistical breakdowns."
    ),
    properties={
        "metric": {
            "type": "string",
            "enum": ["win_rate", "profit_factor", "sharpe_ratio", "expectancy_usd", "mae_mfe_distribution", "holding_time", "rejection_summary", "slippage_summary", "overview"],
            "description": "Metric to calculate (default: 'overview').",
        },
        "group_by": {
            "type": "string",
            "enum": ["session", "market_regime", "symbol", "decision_source", "risk_reward_bucket", "hour", "hour_wib", "hour_utc", "none"],
            "description": "Grouping dimension (e.g. 'session', 'market_regime', 'hour', 'hour_wib').",
        },
        "days_back": {
            "type": "integer",
            "description": "Lookback window in days (default: 90).",
        },
        "symbol": {
            "type": "string",
            "description": "Optional symbol filter (e.g. 'XAUUSD', 'EURUSD').",
        },
        "min_rr": {
            "type": "number",
            "description": "Optional minimum risk-to-reward ratio filter (e.g. 2.0, 2.5).",
        },
    },
    required=["metric"],
)
TELEGRAM_TOOLS.append(RUN_ANALYTICAL_QUERY)

EXPORT_TRADES_TO_EXCEL = _tool(
    name="export_trades_to_excel",
    description="Export completed trade history, holding durations, commissions, and PnL to formatted Excel (.xlsx) file.",
    properties={
        "limit": {"type": "integer", "description": "Maximum number of recent trades to export (default: 200)."},
        "filename": {"type": "string", "description": "Optional output Excel filename (default: trades_export_<timestamp>.xlsx)."},
    },
    required=[],
)

GENERATE_DOCX_REPORT = _tool(
    name="generate_docx_report",
    description="Generate institutional Word (.docx) performance report with quantitative tables, risk metrics, and LLM narrative.",
    properties={
        "title": {"type": "string", "description": "Report title header."},
        "narrative": {"type": "string", "description": "Comprehensive LLM executive narrative synthesis."},
        "filename": {"type": "string", "description": "Optional output filename."},
    },
    required=[],
)

GENERATE_PPTX_DECK = _tool(
    name="generate_pptx_deck",
    description="Generate PowerPoint (.pptx) presentation pitch deck covering multi-agent trading performance and architecture.",
    properties={
        "title": {"type": "string", "description": "Title of presentation deck."},
        "subtitle": {"type": "string", "description": "Subtitle on title slide."},
        "filename": {"type": "string", "description": "Optional output filename."},
    },
    required=[],
)

GENERATE_TEARSHEET_REPORT = _tool(
    name="generate_tearsheet_report",
    description="Generate institutional HTML / PDF performance tearsheet from trading record database.",
    properties={
        "format": {"type": "string", "enum": ["html", "pdf"], "description": "Output format ('html' or 'pdf')."},
        "title": {"type": "string", "description": "Title header for tearsheet."},
    },
    required=[],
)

EXPORT_DATASET_FILE = _tool(
    name="export_dataset_file",
    description="Export database records (paper_trades, asset_analyses, chronicle) to CSV or Apache Parquet file for quantitative analysis.",
    properties={
        "table_name": {"type": "string", "enum": ["paper_trades", "asset_analyses", "chronicle"], "description": "Target database table."},
        "format": {"type": "string", "enum": ["csv", "parquet"], "description": "File format ('csv' or 'parquet')."},
    },
    required=["table_name"],
)

CANCEL_STALE_PENDING_ORDERS = _tool(
    name="cancel_stale_pending_orders",
    description="Cancel resting MT5 pending orders older than max_age_hours.",
    properties={
        "max_age_hours": {"type": "number", "description": "Cancel pending orders older than this age in hours (default: 4.0)."},
    },
    required=[],
)

CLOSE_POSITIONS_BATCH = _tool(
    name="close_positions_batch",
    description="Close open positions filtered by profit, loss, or all without triggering emergency daemon pause.",
    properties={
        "filter_type": {"type": "string", "enum": ["profit_only", "loss_only", "all"], "description": "Filter criteria for closing positions."},
        "reason": {"type": "string", "description": "Reason for batch closing positions."},
    },
    required=["filter_type"],
)

RUN_WALK_FORWARD_ANALYSIS = _tool(
    name="run_walk_forward_analysis",
    description="Run Walk-Forward Analysis (WFA) on trading strategy to evaluate out-of-sample statistical robustness.",
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'EURUSD', 'BTCUSD')."},
        "strategy": {"type": "string", "description": "Strategy name to backtest."},
        "n_folds": {"type": "integer", "description": "Number of walk-forward rolling folds (default: 4)."},
    },
    required=["symbol"],
)

RUN_PARAMETER_PLATEAU_OPTIMIZATION = _tool(
    name="run_parameter_plateau_optimization",
    description="Run Parameter Flat Plateau Optimization to find robust, curve-fitting-resistant parameter regions.",
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'EURUSD')."},
        "n_trials": {"type": "integer", "description": "Number of optimization trials (default: 25)."},
    },
    required=["symbol"],
)

GET_MACRO_PRICED_IN_SCORE = _tool(
    name="get_macro_priced_in_score",
    description="Calculate macroeconomic priced-in score and saturation analysis using COT percentiles, retail sentiment, FedWatch probabilities, and ATR run-ups.",
    properties={
        "symbol": {"type": "string", "description": "Currency pair or asset (e.g. 'EURUSD', 'USDJPY', 'XAUUSD')."},
        "cot_percentile": {"type": "number", "description": "COT positioning percentile (0-100)."},
        "retail_sentiment": {"type": "number", "description": "Retail long percentage (0-100)."},
        "fedwatch_dominant_prob": {"type": "number", "description": "Dominant rate outcome probability (0-100)."},
        "eurusd_run_up_vs_atr": {"type": "number", "description": "Recent move extension relative to ATR."},
        "fedwatch_repricing_delta": {"type": "number", "description": "FedWatch shift percentage delta."},
    },
    required=["symbol"],
)

GET_SYNTHETIC_CROSS_RATE = _tool(
    name="get_synthetic_cross_rate",
    description="Calculate synthetic cross-rate, spread, and synthetic ATR from USD-based majors for non-universe pairs (e.g. GBPJPY, EURGBP, EURJPY, AUDJPY, EURAUD, GBPAUD).",
    properties={
        "pair": {"type": "string", "description": "Cross pair to synthesize (e.g. 'GBPJPY', 'EURGBP', 'EURJPY', 'AUDJPY')."},
        "timeframe": {"type": "string", "description": "Timeframe for ATR calculation (e.g. 'H1', 'H4', 'D1')."},
    },
    required=["pair"],
)

NEW_OFFICE_AND_QUANT_TOOLS = [
    EXPORT_TRADES_TO_EXCEL,
    GENERATE_DOCX_REPORT,
    GENERATE_PPTX_DECK,
    GENERATE_TEARSHEET_REPORT,
    EXPORT_DATASET_FILE,
    CANCEL_STALE_PENDING_ORDERS,
    CLOSE_POSITIONS_BATCH,
    RUN_WALK_FORWARD_ANALYSIS,
    RUN_PARAMETER_PLATEAU_OPTIMIZATION,
    GET_MACRO_PRICED_IN_SCORE,
    GET_SYNTHETIC_CROSS_RATE,
]

SEARCH_TOOLS_TOOL = _tool(
    name="search_tools",
    description="Semantic and keyword discovery of available tools across the registry. Find tools by capability, indicator name, data type, or asset class without loading all schemas.",
    properties={
        "query": {"type": "string", "description": "Keywords or capability to search for (e.g. 'volatility', 'order flow', 'news', 'yields')."},
        "limit": {"type": "integer", "description": "Maximum number of tools to return (default 5)."},
    },
    required=["query"],
)

GET_GRADUATION_STATUS_TOOL = _tool(
    name="get_graduation_status",
    description="Evaluate trader's paper trading graduation progress toward live qualification (trades count, win rate, profit factor, max drawdown).",
    properties={},
    required=[],
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

ADD_JOURNAL_ENTRY_TOOL = _tool(
    name="add_journal_entry",
    description="Add a qualitative trading journal entry with emotional state, lessons learned, and tags.",
    properties={
        "content": {"type": "string", "description": "Journal entry text."},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional list of tags (e.g. ['FOMO', 'Gold', 'Discipline'])."},
        "sentiment": {"type": "string", "description": "Emotional state (e.g. 'neutral', 'disciplined', 'fomo', 'revenge')."},
    },
    required=["content"],
)

GET_JOURNAL_ENTRIES_TOOL = _tool(
    name="get_journal_entries",
    description="Retrieve past trading journal entries with optional tag filter.",
    properties={
        "limit": {"type": "integer", "description": "Max entries to retrieve (default 20)."},
        "tag": {"type": "string", "description": "Optional tag filter."},
    },
    required=[],
)

READ_SYSTEM_LOGS_TOOL = _tool(
    name="read_system_logs",
    description="Safely read recent system activity logs from monika.log with optional line count and query filter.",
    properties={
        "file_name": {"type": "string", "description": "Log file name (default 'monika.log')."},
        "lines": {"type": "integer", "description": "Number of lines to read (default 50, max 200)."},
        "filter_query": {"type": "string", "description": "Optional search term to filter log lines."},
    },
    required=[],
)

GET_SYMBOL_SPECIFICATION = _tool(
    name="get_symbol_specification",
    description="Get exact instrument specifications including contract size, pip size, pip value in USD, digits, and lot limits.",
    properties={
        "symbol": {"type": "string", "description": "Symbol name or shorthand (e.g. 'XAUUSD', 'EURUSD', 'BTCUSD', 'US30')."},
    },
    required=["symbol"],
)

RESTART_MT5_SERVICE_TOOL = _tool(
    name="restart_mt5_service",
    description="Safely cycle and restart the MT5 connection/service bridge to recover from hangs or timeouts.",
    properties={
        "force": {"type": "boolean", "description": "Force reconnect even if currently reported as connected. Default: true."},
        "reason": {"type": "string", "description": "Reason for restarting MT5 connection (for audit logs)."},
    },
    required=[],
)

UPDATE_CONFIG_PARAMETER_TOOL = _tool(
    name="update_config_parameter",
    description="Safely update a configuration parameter in settings.yaml using atomic writes (e.g. 'trading.risk.risk_per_trade_pct').",
    properties={
        "key": {"type": "string", "description": "Dot-separated configuration key path (e.g. 'trading.risk.risk_per_trade_pct' or 'paper_trading.enabled')."},
        "value": {"type": "string", "description": "New value to set (will be auto-cast to number, bool, or string)."},
        "reason": {"type": "string", "description": "Reason for the configuration change (for audit logs)."},
    },
    required=["key", "value"],
)

REMEDIATION_NEW_TOOLS = [
    SEARCH_TOOLS_TOOL,
    GET_ECONOMIC_SURPRISE,
    GET_GRADUATION_STATUS_TOOL,
    SIMULATE_PRICE_SHOCK_TOOL,
    ADD_JOURNAL_ENTRY_TOOL,
    GET_JOURNAL_ENTRIES_TOOL,
    READ_SYSTEM_LOGS_TOOL,
    GET_SYMBOL_SPECIFICATION,
    RESTART_MT5_SERVICE_TOOL,
    UPDATE_CONFIG_PARAMETER_TOOL,
]

for t in REMEDIATION_NEW_TOOLS:
    if t not in TELEGRAM_TOOLS:
        TELEGRAM_TOOLS.append(t)

for smc_tool in [GET_INDUCEMENTS, GET_BREAKER_BLOCKS, GET_JUDAS_SWING, GET_EQUAL_HIGHS_LOWS, GET_WICK_TO_WICK_FVG, GET_INVERTED_FVG]:
    if smc_tool not in TELEGRAM_TOOLS:
        TELEGRAM_TOOLS.append(smc_tool)


if EXECUTE_ANALYSIS_CODE not in TELEGRAM_TOOLS:
    TELEGRAM_TOOLS.append(EXECUTE_ANALYSIS_CODE)
if TRIGGER_MARKET_SCAN not in TELEGRAM_TOOLS:
    TELEGRAM_TOOLS.append(TRIGGER_MARKET_SCAN)
if GET_PNL_SUMMARY not in TELEGRAM_TOOLS:
    TELEGRAM_TOOLS.append(GET_PNL_SUMMARY)

for t in NEW_OFFICE_AND_QUANT_TOOLS:
    if t not in TELEGRAM_TOOLS:
        TELEGRAM_TOOLS.append(t)

QUERY_DATABASE_SQL = _tool(
    name="query_database_sql",
    description="Execute read-only SELECT query directly on PostgreSQL database with safety guardrails and 50 row limit (Admin only).",
    properties={
        "sql": {"type": "string", "description": "Read-only SELECT SQL statement (e.g. 'SELECT * FROM paper_trade_records WHERE pnl_pct > 0 ORDER BY id DESC LIMIT 10')"}
    },
    required=["sql"]
)

CAPTURE_TERMINAL_SCREENSHOT = _tool(
    name="capture_terminal_screenshot",
    description="Captures live terminal/desktop screenshot or renders high-fidelity visual status card delivered directly to chat.",
    properties={},
    required=[]
)

GET_SERVER_TELEMETRY = _tool(
    name="get_server_telemetry",
    description="Retrieve live server hardware telemetry (CPU, RAM, disk space, host uptime, top background process PIDs).",
    properties={},
    required=[]
)

GET_BROKER_EXPENSES_SUMMARY = _tool(
    name="get_broker_expenses_summary",
    description="Aggregates broker expenses (commissions, overnight swap fees, and account financing charges) over a time window.",
    properties={
        "days": {"type": "integer", "description": "Lookback window in days (default 30)."},
        "symbol": {"type": "string", "description": "Optional symbol filter (e.g. 'EURUSD')."}
    },
    required=[]
)

GET_ACTIVE_NEGATIVE_CONSTRAINTS = _tool(
    name="get_active_negative_constraints",
    description="List active negative constraints ('DO NOT' rules) derived from past trade reflections to prevent recurring errors.",
    properties={
        "symbol": {"type": "string", "description": "Optional symbol to filter constraints (e.g. 'EURUSD')."}
    },
    required=[]
)

GET_SMT_DIVERGENCE = _tool(
    name="get_smt_divergence",
    description="Detect Smart Money Technique (SMT) divergence between correlated or inversely correlated pairs (e.g. EURUSD vs DXY).",
    properties={
        "symbol": {"type": "string", "description": "Primary trading symbol (e.g. 'EURUSD')."},
        "compared_to": {"type": "string", "description": "Benchmark or correlated asset (e.g. 'DXY', 'GBPUSD')."},
        "timeframe": {"type": "string", "description": "Candle timeframe (e.g. 'H1', 'H4')."},
        "lookback": {"type": "integer", "description": "Lookback bars (default 30)."}
    },
    required=["symbol"]
)

TERMINAL_TOOL = _tool(
    name="terminal",
    description="Execute command line shell commands in workspace environment or check background processes.",
    properties={
        "command": {"type": "string", "description": "The shell command string to execute."},
        "workdir": {"type": "string", "description": "Optional working directory."},
        "timeout": {"type": "number", "description": "Timeout in seconds (default 60)."},
        "background": {"type": "boolean", "description": "Run command asynchronously in background if True."}
    },
    required=["command"]
)

COMPUTER_USE_TOOL = _tool(
    name="computer_use",
    description="Interact with desktop GUI applications (MetaTrader 5 terminal) via screenshot, mouse clicks, keystrokes, and text typing.",
    properties={
        "action": {"type": "string", "enum": ["screenshot", "mouse_move", "left_click", "right_click", "type_text", "key_press"], "description": "GUI action to perform."},
        "coordinate": {"type": "array", "items": {"type": "integer"}, "description": "Screen [x, y] pixel coordinates for mouse action."},
        "text": {"type": "string", "description": "Text to type into active window."},
        "key": {"type": "string", "description": "Key to press (e.g. 'enter', 'tab', 'f9', 'ctrl+s')."}
    },
    required=["action"]
)

CALCULATE_CONFLUENCE_TOOL = _tool(
    name="calculate_confluence",
    description="Calculates multi-layer analytical confluence score (0.0 to 1.0) and technical alignment across HTF/LTF, market regime, order blocks, and momentum.",
    properties={
        "symbol": {"type": "string", "description": "Trading pair or instrument (e.g. 'EURUSD', 'XAUUSD')."},
        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Trade setup direction to evaluate."}
    },
    required=["symbol", "direction"]
)

GET_SLIPPAGE_SUMMARY_TOOL = _tool(
    name="get_slippage_summary",
    description="Retrieve execution slippage telemetry, average positive/negative slippage, and execution drift statistics across broker fills.",
    properties={
        "symbol": {"type": "string", "description": "Optional symbol filter."},
        "days_back": {"type": "integer", "description": "Lookback window in days (default: 30)."}
    },
    required=[]
)

BACKUP_DATABASE_TOOL = _tool(
    name="backup_database",
    description="Trigger an on-demand compressed PostgreSQL database backup via pg_dump to the backups/ directory (Admin only).",
    properties={
        "force": {"type": "boolean", "description": "Force backup even if automated backup is disabled in settings.yaml (default: true)."}
    },
    required=[]
)

COMPILE_MQL5_EA_TOOL = _tool(
    name="compile_mql5_ea",
    description="Compile an MQL5 source file (.mq5) into executable binary (.ex5) using metaeditor64.exe headless compiler.",
    properties={
        "source_path": {"type": "string", "description": "Path to the .mq5 source file to compile."}
    },
    required=["source_path"]
)

GET_MT5_BROKER_LOGS_TOOL = _tool(
    name="get_mt5_broker_logs",
    description="Read recent log entries from the MetaTrader 5 broker terminal text logs in the MT5 data directory.",
    properties={
        "lines": {"type": "integer", "description": "Number of recent lines to read (default 20)."},
        "date": {"type": "string", "description": "Optional log date in YYYYMMDD format (defaults to current date)."}
    },
    required=[]
)

GET_MT5_TERMINAL_INFO_TOOL = _tool(
    name="get_mt5_terminal_info",
    description="Inspect MetaTrader 5 terminal status, trade permissions (Algo Trading button status: Hijau vs Merah), and broker connection.",
    properties={},
    required=[]
)

ENHANCEMENT_TOOLS = [
    QUERY_DATABASE_SQL,
    CAPTURE_TERMINAL_SCREENSHOT,
    GET_SERVER_TELEMETRY,
    GET_BROKER_EXPENSES_SUMMARY,
    GET_ACTIVE_NEGATIVE_CONSTRAINTS,
    GET_SMT_DIVERGENCE,
    TERMINAL_TOOL,
    COMPUTER_USE_TOOL,
    CALCULATE_CONFLUENCE_TOOL,
    GET_SLIPPAGE_SUMMARY_TOOL,
    BACKUP_DATABASE_TOOL,
    COMPILE_MQL5_EA_TOOL,
    GET_MT5_BROKER_LOGS_TOOL,
    GET_MT5_TERMINAL_INFO_TOOL,
]


for t in ENHANCEMENT_TOOLS:
    if t not in TELEGRAM_TOOLS:
        TELEGRAM_TOOLS.append(t)


# =============================================================================
# Capability Gap Remediation Tools (15 Tools)
# =============================================================================

GET_PIVOT_POINTS = _tool(
    name="get_pivot_points",
    description="Calculate Classic, Camarilla, and Woodie pivot points, support (S1-S4), and resistance (R1-R4) levels for a given symbol.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD'). Defaults to watchlist primary."},
        "timeframe": {"type": "string", "enum": ["D1", "W1", "M1"], "description": "Base calculation timeframe (default: 'D1')."},
        "method": {"type": "string", "enum": ["all", "classic", "camarilla", "woodie"], "description": "Pivot calculation formula (default: 'all')."}
    },
    required=[]
)

GET_ICHIMOKU = _tool(
    name="get_ichimoku",
    description="Compute full Ichimoku Kinko Hyo cloud indicator: Tenkan-sen (Conversion), Kijun-sen (Base), Senkou Span A/B (Cloud), and Chikou Span (Lagging).",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["M15", "M30", "H1", "H4", "D1"], "description": "Chart timeframe (default: 'H1')."},
        "tenkan": {"type": "integer", "description": "Tenkan period (default: 9)."},
        "kijun": {"type": "integer", "description": "Kijun period (default: 26)."},
        "senkou_b": {"type": "integer", "description": "Senkou Span B period (default: 52)."}
    },
    required=[]
)

SCAN_CHART_PATTERNS = _tool(
    name="scan_chart_patterns",
    description="Scan price action for classic and harmonic chart patterns: Double Top/Bottom, Head and Shoulders / Inverse H&S, Gartley, Bat, Butterfly, and Crab.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"], "description": "Chart timeframe (default: 'H1')."},
        "lookback": {"type": "integer", "description": "Number of bars to analyze (default: 150)."}
    },
    required=[]
)

GET_SEASONALITY = _tool(
    name="get_seasonality",
    description="Calculate historical seasonality statistics: monthly returns, day-of-week win rates, and calendar tendencies across multi-year historical data.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["monthly", "day_of_week", "all"], "description": "Seasonality analysis grouping (default: 'all')."},
        "years": {"type": "integer", "description": "Historical lookback in years (default: 5)."}
    },
    required=[]
)

GET_DIVERGENCES = _tool(
    name="get_divergences",
    description="Detect regular and hidden momentum divergences between price swings and technical oscillators (RSI, MACD, Stochastic).",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"], "description": "Chart timeframe (default: 'H1')."},
        "indicator": {"type": "string", "enum": ["all", "rsi", "macd", "stochastic"], "description": "Oscillator indicator to evaluate (default: 'all')."}
    },
    required=[]
)

GET_RECENT_TICK_FLOW = _tool(
    name="get_recent_tick_flow",
    description="Retrieve recent high-frequency tick data flow: Bid/Ask spread, tick volume, micro-delta, and buy/sell pressure ratio directly from MT5.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "count": {"type": "integer", "description": "Number of recent ticks to inspect (default: 100, max: 1000)."}
    },
    required=[]
)

EXPORT_TICK_DATA = _tool(
    name="export_tick_data",
    description="Export historical raw tick data to CSV file and prepare download link for quantitative tick analysis.",
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "hours": {"type": "integer", "description": "Number of hours of tick history to export (default: 4, max: 24)."},
        "filename": {"type": "string", "description": "Optional custom export filename."}
    },
    required=[]
)

GET_LATENCY_BREAKDOWN = _tool(
    name="get_latency_breakdown",
    description="Inspect internal system latency telemetry: MT5 order round-trip ping, SQLite/PostgreSQL query timings, and LLM inference response times.",
    properties={},
    required=[]
)

BROWSER_TOOL = _tool(
    name="browser",
    description="Headless/interactive DrissionPage web browser automation. Overcomes Cloudflare, anti-bot protections, JavaScript-rendered dashboards, and paywalls.",
    properties={
        "action": {"type": "string", "enum": ["open", "extract", "click", "type", "screenshot", "close"], "description": "Browser action to execute."},
        "url": {"type": "string", "description": "Target webpage URL (required for 'open')."},
        "selector": {"type": "string", "description": "CSS selector or element text for extract, click, or type."},
        "text": {"type": "string", "description": "Text to input for 'type' action."}
    },
    required=["action"]
)

SAVE_SCRIPT = _tool(
    name="save_script",
    description="Save a custom Python analysis, backtest, or quantitative script to persistent storage (data/user_scripts/) for re-execution across sessions.",
    properties={
        "script_name": {"type": "string", "description": "Unique filename for the script (e.g. 'volatility_model.py')."},
        "code": {"type": "string", "description": "Executable Python code containing analysis logic."},
        "description": {"type": "string", "description": "Optional brief description of what the script does."}
    },
    required=["script_name", "code"]
)

LIST_SAVED_SCRIPTS = _tool(
    name="list_saved_scripts",
    description="List all persisted custom Python quantitative and backtest scripts saved in data/user_scripts/.",
    properties={},
    required=[]
)

RUN_SAVED_SCRIPT = _tool(
    name="run_saved_script",
    description="Execute a previously saved Python script from data/user_scripts/ in the sandboxed runtime and capture output.",
    properties={
        "script_name": {"type": "string", "description": "Name of the script to execute (e.g. 'volatility_model.py')."}
    },
    required=["script_name"]
)

GET_INDONESIA_MACRO = _tool(
    name="get_indonesia_macro",
    description="Retrieve Bank Indonesia monetary policy indicators: BI-Rate, JISDOR USD/IDR reference rate, and BPS macroeconomic stats (Inflation YoY/MoM, Trade Balance).",
    properties={},
    required=[]
)

GET_EARNINGS_CALENDAR = _tool(
    name="get_earnings_calendar",
    description="Fetch upcoming corporate earnings releases, EPS consensus estimates, revenue forecasts, and earnings release dates from Finnhub/financial calendar.",
    properties={
        "symbol": {"type": "string", "description": "Optional specific stock ticker (e.g. 'AAPL', 'NVDA', 'MSFT')."},
        "days_ahead": {"type": "integer", "description": "Lookahead horizon in days (default: 7)."}
    },
    required=[]
)

SEARCH_SOCIAL_SENTIMENT = _tool(
    name="search_social_sentiment",
    description="Search real-time financial market sentiment, retail buzz, and breaking trader commentary on Twitter/X, Reddit, or web search.",
    properties={
        "query": {"type": "string", "description": "Search query or ticker cashtag (e.g. '$XAUUSD', '$BTC', 'Federal Reserve')."},
        "limit": {"type": "integer", "description": "Maximum number of sentiment items to return (default: 10)."}
    },
    required=["query"]
)

REMEDIATION_GAP_TOOLS = [
    GET_PIVOT_POINTS,
    GET_ICHIMOKU,
    SCAN_CHART_PATTERNS,
    GET_SEASONALITY,
    GET_DIVERGENCES,
    GET_RECENT_TICK_FLOW,
    EXPORT_TICK_DATA,
    GET_LATENCY_BREAKDOWN,
    BROWSER_TOOL,
    SAVE_SCRIPT,
    LIST_SAVED_SCRIPTS,
    RUN_SAVED_SCRIPT,
    GET_INDONESIA_MACRO,
    GET_EARNINGS_CALENDAR,
    SEARCH_SOCIAL_SENTIMENT,
]

for t in REMEDIATION_GAP_TOOLS:
    if t not in TELEGRAM_TOOLS:
        TELEGRAM_TOOLS.append(t)

# =============================================================================
# Full Capability Upgrade Tools (12 New Tools)
# =============================================================================

SIMULATE_PORTFOLIO_DRAWDOWN_TOOL = _tool(
    name="simulate_portfolio_drawdown",
    description="Simulate combined margin, SL loss in USD, and correlated portfolio heat for hypothetical simultaneous positions (Q099).",
    properties={
        "positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "direction": {"type": "string", "enum": ["buy", "sell"]},
                    "lots": {"type": "number"},
                    "entry": {"type": "number"},
                    "sl": {"type": "number"}
                },
                "required": ["symbol", "direction", "lots"]
            },
            "description": "List of hypothetical positions to evaluate simultaneously."
        }
    },
    required=["positions"]
)

CALCULATE_KELLY_CRITERION_TOOL = _tool(
    name="calculate_kelly_criterion",
    description="Calculates Full Kelly, Half Kelly fraction, and risk sizing from closed trade win rate and payoff ratio (Q100).",
    properties={
        "symbol": {"type": "string", "description": "Optional symbol filter."},
        "horizon": {"type": "string", "enum": ["all_time", "90d", "30d"], "description": "Lookback horizon (default: 'all_time')."}
    },
    required=[]
)

RUN_WALK_FORWARD_OPTIMIZATION_TOOL = _tool(
    name="run_walk_forward_optimization",
    description="Run Walk-Forward Optimization across chronological folds with purge gaps and embargo to test for overfitting (Q102).",
    properties={
        "strategy": {"type": "string", "description": "Strategy identifier (e.g. 'smc_fvg', 'liquidity_sweep')."},
        "symbol": {"type": "string", "description": "Instrument symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "n_folds": {"type": "integer", "description": "Number of rolling train/test folds (default: 4)."}
    },
    required=["strategy", "symbol"]
)

OPTIMIZE_STRATEGY_PARAMETERS_TOOL = _tool(
    name="optimize_strategy_parameters",
    description="Run a parameter grid-search backtest over a specified range to find optimal Profit Factor and Sharpe (Q111).",
    properties={
        "strategy": {"type": "string", "description": "Strategy name (e.g. 'smc_fvg')."},
        "symbol": {"type": "string", "description": "Instrument symbol (e.g. 'XAUUSD')."},
        "param_name": {"type": "string", "description": "Parameter name to optimize (e.g. 'atr_period')."},
        "min_val": {"type": "number", "description": "Starting parameter value."},
        "max_val": {"type": "number", "description": "Ending parameter value."},
        "step": {"type": "number", "description": "Step increment (default: 1)."}
    },
    required=["strategy", "symbol", "param_name", "min_val", "max_val"]
)

RUN_MODEL_BENCHMARK_TOOL = _tool(
    name="run_model_benchmark",
    description="Benchmark trading LLMs head-to-head via Alpha Arena Elo tournament on decision accuracy and latency (Q112).",
    properties={
        "models": {"type": "array", "items": {"type": "string"}, "description": "List of model IDs to test."},
        "rounds": {"type": "integer", "description": "Number of benchmark rounds (default: 3)."}
    },
    required=[]
)

EVALUATE_DEBATE_EFFICACY_TOOL = _tool(
    name="evaluate_debate_efficacy",
    description="Evaluate whether Bull vs Bear dialectical debate improved trade win rates and filtered out losing setups (Q140).",
    properties={
        "days_back": {"type": "integer", "description": "Lookback window in days (default: 90)."}
    },
    required=[]
)

SCAN_SMC_SETUPS_TOOL = _tool(
    name="scan_smc_setups",
    description="Parallel live screener scanning all pairs for active unmitigated Order Blocks, FVGs, and Liquidity Sweeps (Q060).",
    properties={
        "symbols": {"type": "array", "items": {"type": "string"}, "description": "Optional list of symbols to screen (default: all universe)."},
        "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"], "description": "Timeframe to scan (default: 'H4')."}
    },
    required=[]
)

GET_CARRY_TRADE_RANKINGS_TOOL = _tool(
    name="get_carry_trade_rankings",
    description="Calculate risk-adjusted carry trade attractiveness (Rate Spread / Realized Volatility) across currency pairs (Q074).",
    properties={
        "min_spread": {"type": "number", "description": "Minimum nominal rate spread in percent (default: 0.5)."}
    },
    required=[]
)

GET_COMMODITY_SPREAD_TOOL = _tool(
    name="get_commodity_spread",
    description="Calculates live commodity spreads (Brent vs WTI crude oil), 20-day rolling mean, and z-score for stat-arb (Q088).",
    properties={
        "primary_symbol": {"type": "string", "description": "Primary commodity (default: 'XBRUSD')."},
        "secondary_symbol": {"type": "string", "description": "Secondary commodity (default: 'XTIUSD')."}
    },
    required=[]
)

GET_MT5_CHART_OBJECTS_TOOL = _tool(
    name="get_mt5_chart_objects",
    description="Extract user-drawn S/R lines, trendlines, Fibonacci levels, and indicator parameters from the active MT5 chart (Q151).",
    properties={
        "symbol": {"type": "string", "description": "Chart instrument symbol (default: 'XAUUSD')."}
    },
    required=[]
)

CAPTURE_MT5_CHART_SCREENSHOT_TOOL = _tool(
    name="capture_mt5_chart_screenshot",
    description="Capture an on-demand screenshot of the active MT5 chart window and prepare it for Multimodal Vision inspection (Q151).",
    properties={
        "symbol": {"type": "string", "description": "Chart instrument symbol (default: 'XAUUSD')."},
        "timeframe": {"type": "string", "description": "Chart timeframe (default: 'H1')."},
        "width": {"type": "integer", "description": "Image width in pixels (default: 1280)."},
        "height": {"type": "integer", "description": "Image height in pixels (default: 720)."}
    },
    required=[]
)

PLOT_EQUITY_CURVE_TOOL = _tool(
    name="plot_equity_curve",
    description="Plot and deliver inline PNG equity curve chart with drawdown bands directly into Telegram chat (Q013).",
    properties={
        "days_back": {"type": "integer", "description": "Historical days back to plot (default: 90)."}
    },
    required=[]
)

NEW_CAPABILITY_UPGRADE_TOOLS = [
    SIMULATE_PORTFOLIO_DRAWDOWN_TOOL,
    CALCULATE_KELLY_CRITERION_TOOL,
    RUN_WALK_FORWARD_OPTIMIZATION_TOOL,
    OPTIMIZE_STRATEGY_PARAMETERS_TOOL,
    RUN_MODEL_BENCHMARK_TOOL,
    EVALUATE_DEBATE_EFFICACY_TOOL,
    SCAN_SMC_SETUPS_TOOL,
    GET_CARRY_TRADE_RANKINGS_TOOL,
    GET_COMMODITY_SPREAD_TOOL,
    GET_MT5_CHART_OBJECTS_TOOL,
    CAPTURE_MT5_CHART_SCREENSHOT_TOOL,
    PLOT_EQUITY_CURVE_TOOL,
    GET_ECB_QT_PROGRESS,
    GET_GLOBAL_PMI_TREND,
]

for t in NEW_CAPABILITY_UPGRADE_TOOLS:
    if t not in TELEGRAM_TOOLS:
        TELEGRAM_TOOLS.append(t)
    if t not in STAGE2_TOOLS:
        STAGE2_TOOLS.append(t)

# All tools (for reference/testing)
ALL_TOOLS: list[dict] = list({t["name"]: t for t in STAGE1_TOOLS + STAGE1_TOOLS_WEEKEND_BTC + STAGE2_TOOLS + TELEGRAM_TOOLS + STAGE2_ESSENTIAL_TOOLS + STAGE2_FROZEN_TOOLS + NEW_OFFICE_AND_QUANT_TOOLS + REMEDIATION_NEW_TOOLS + ENHANCEMENT_TOOLS + REMEDIATION_GAP_TOOLS + [GET_VERIFIED_MARKET_SNAPSHOT, GET_MARKET_QUOTE, EXECUTE_ANALYSIS_CODE, RETRIEVE_SPILLED_CONTEXT, DELEGATE_SPECIALIST_ANALYSIS, SKILLS_LIST_TOOL, SKILL_VIEW_TOOL, SEARCH_HISTORICAL_MEMORIES, MANAGE_CRON, QUERY_SIGNAL_PERFORMANCE, GET_LATEST_RISK_VERDICT, EXPORT_DEBATE_TRANSCRIPTS, TRIGGER_LEARNING_CYCLE, RUN_SYSTEM_DOCTOR_CHECK, SET_TRAILING_STOP, EXPORT_HISTORICAL_DATA_CSV, TRIGGER_MARKET_SCAN, RUN_STRATEGY_BACKTEST, GET_PNL_SUMMARY, PLOT_PRICE_CHART, DETECT_CANDLESTICK_PATTERNS, RUN_ADHOC_SYMBOL_DEBATE, RUN_HOSTILE_STRESS_TEST, RUN_ANALYTICAL_QUERY, GET_INDUCEMENTS, GET_BREAKER_BLOCKS, GET_JUDAS_SWING, GET_EQUAL_HIGHS_LOWS, GET_WICK_TO_WICK_FVG, GET_INVERTED_FVG]}.values())





def minify_tool_definitions(tools: list[dict]) -> list[dict]:
    """
    Pi Minimal Tool Schemas: Strips superfluous narrative prose while preserving
    exact parameter keys, types, enums, required constraints, and primary description.
    Saves up to 60% declaration tokens across multi-turn agent loops.
    """
    minified = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        m_tool = dict(t)
        raw_desc = m_tool.get("description", "")
        if raw_desc:
            first_line = raw_desc.strip().split("\n")[0].split(". ")[0].strip()
            m_tool["description"] = first_line if first_line.endswith(".") else f"{first_line}."

        schema = m_tool.get("input_schema")
        if isinstance(schema, dict):
            new_schema = dict(schema)
            props = new_schema.get("properties")
            if isinstance(props, dict):
                new_props = {}
                for p_name, p_val in props.items():
                    if isinstance(p_val, dict):
                        cp = dict(p_val)
                        p_desc = cp.get("description", "")
                        if p_desc and len(p_desc) > 80:
                            cp["description"] = p_desc.split(". ")[0].split("\n")[0].strip()
                        new_props[p_name] = cp
                    else:
                        new_props[p_name] = p_val
                new_schema["properties"] = new_props
            m_tool["input_schema"] = new_schema
        minified.append(m_tool)
    return minified


def make_strict_tool_definitions(tools: list[dict]) -> list[dict]:
    """
    DeepSeek / OpenAI strict schema compliance:
    Ensures all properties are declared in required and additionalProperties is False.
    """
    strict_tools = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        st = dict(t)
        schema = st.get("input_schema")
        if isinstance(schema, dict):
            sc = dict(schema)
            sc["additionalProperties"] = False
            props = sc.get("properties", {})
            if isinstance(props, dict):
                sc["required"] = list(props.keys())
            st["input_schema"] = sc
        strict_tools.append(st)
    return strict_tools

