# ==============================================================================
# File: application/analysis/tools/definitions/macro.py
# ==============================================================================

"""
Macroeconomic, news, interest rate, yield, and central bank tool definitions.
"""

from __future__ import annotations

from monika.application.analysis.tools.definitions.base import _tool

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
        "report_type": {
            "type": "string",
            "description": "CPI, NFP, PCE, PPI, JOLTS, ISM_MANUFACTURING, ISM_SERVICES, UMICH",
        },
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


GET_MACRO_BIAS_SCORE = _tool(
    name="get_macro_bias_score",
    description="Deterministic macro pressure score (10Y yield momentum + policy rate proxy, NOT true real yield — see output for caveat). Informational; a hard gate re-validates it against your actual decision at submission and REJECTS buy/sell that strongly contradicts it.",
    properties={"symbol": {"type": "string"}},
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


GET_INDONESIA_MACRO = _tool(
    name="get_indonesia_macro",
    description="Retrieve Bank Indonesia monetary policy indicators: BI-Rate, JISDOR USD/IDR reference rate, and BPS macroeconomic stats (Inflation YoY/MoM, Trade Balance).",
    properties={},
    required=[],
)


GET_EARNINGS_CALENDAR = _tool(
    name="get_earnings_calendar",
    description="Fetch upcoming corporate earnings releases, EPS consensus estimates, revenue forecasts, and earnings release dates from Finnhub/financial calendar.",
    properties={
        "symbol": {"type": "string", "description": "Optional specific stock ticker (e.g. 'AAPL', 'NVDA', 'MSFT')."},
        "days_ahead": {"type": "integer", "description": "Lookahead horizon in days (default: 7)."},
    },
    required=[],
)


__all__ = [
    "GET_ECONOMIC_CALENDAR",
    "GET_WEEKLY_MACRO_SUMMARY",
    "GET_NEWS_DIGEST",
    "GET_NEWS_ITEMS",
    "GET_TREASURY_YIELDS",
    "GET_BOND_YIELD_SPREADS",
    "GET_INTEREST_RATES",
    "GET_FEDWATCH_PROBABILITIES",
    "GET_CENTRAL_BANK_EXPECTATIONS",
    "GET_COT_REPORT",
    "GET_VIX",
    "GET_EIA_OIL_INVENTORY",
    "GET_FEAR_GREED",
    "GET_ECONOMIC_SURPRISE",
    "GET_PRECOMPUTED_COT_SIGNALS",
    "GET_SURPRISE_SUMMARY",
    "INSPECT_ECONOMIC_REPORT",
    "DIFF_CENTRAL_BANK_DOCUMENTS",
    "GET_MACRO_CROSS_REPORT_SYNTHESIS",
    "GET_G10_MACRO_DIVERGENCE",
    "GET_FED_NET_LIQUIDITY_AND_STRESS",
    "GET_TREASURY_AUCTION_RESULTS",
    "GET_ECB_QT_PROGRESS",
    "GET_GLOBAL_PMI_TREND",
    "GET_MACRO_BIAS_SCORE",
    "GET_MACRO_PRICED_IN_SCORE",
    "GET_INDONESIA_MACRO",
    "GET_EARNINGS_CALENDAR",
]
