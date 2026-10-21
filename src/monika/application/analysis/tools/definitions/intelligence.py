# ==============================================================================
# File: application/analysis/tools/definitions/intelligence.py
# ==============================================================================

"""
Market intelligence, web research, sentiment, notes, and memory tool definitions.
"""

from __future__ import annotations

from monika.application.analysis.tools.definitions.base import _tool

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


GET_CONVERSATION_HISTORY = _tool(
    name="get_conversation_history",
    description="Fetch previous Telegram conversation messages for context continuity.",
    properties={
        "limit": {"type": "integer", "description": "Number of most recent messages to fetch. Default: 20."},
    },
    required=[],
)


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
    description=("List all active, non-expired market intelligence and operator directives stored in the database."),
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


GET_STRUCTURED_SENTIMENT = {
    "name": "get_structured_sentiment",
    "description": "Mengambil sentimen teragregasi dan terstruktur dari institusional (COT), retail, dan VIX untuk sebuah aset.",
    "input_schema": {
        "type": "object",
        "properties": {"symbol": {"type": "string", "description": "Contoh: EURUSD"}},
        "required": ["symbol"],
    },
}


UPDATE_SCRATCHPAD = _tool(
    name="update_scratchpad",
    description=(
        "Updates active working scratchpad with verified calculation anchors. "
        "Use this to record H4 ATR, ADR bounds, structural SL level, target TP, invalidation, "
        "and confirmed confluences. Preserved across all compaction turns."
    ),
    properties={
        "bias": {
            "type": "string",
            "enum": ["BULLISH", "BEARISH", "NEUTRAL"],
            "description": "Dominant directional bias",
        },
        "h4_atr": {"type": "number", "description": "Verified H4 ATR 14 value"},
        "daily_adr": {"type": "number", "description": "Verified 5-day Average Daily Range (ADR)"},
        "invalidation_price": {"type": "number", "description": "Price level that invalidates the trade thesis"},
        "entry_zone": {
            "type": "object",
            "properties": {"low": {"type": "number"}, "high": {"type": "number"}, "type": {"type": "string"}},
        },
        "structural_sl": {"type": "object", "properties": {"price": {"type": "number"}, "basis": {"type": "string"}}},
        "target_tp": {"type": "object", "properties": {"price": {"type": "number"}, "basis": {"type": "string"}}},
        "rr_ratio": {"type": "number", "description": "Projected Reward-to-Risk ratio (must be >= 1.50)"},
        "confluence_score": {"type": "number", "description": "Composite confluence score out of 14"},
        "verified_confluences": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of confirmed confluence tags",
        },
        "notes": {"type": "array", "items": {"type": "string"}, "description": "Short analytical bullet points"},
    },
    required=[],
)


READ_SCRATCHPAD = _tool(
    name="read_scratchpad",
    description="Reads current working scratchpad state and recorded analytical anchors.",
    properties={},
    required=[],
)


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


SEARCH_TOOLS_TOOL = _tool(
    name="search_tools",
    description="Semantic and keyword discovery of available tools across the registry. Find tools by capability, indicator name, data type, or asset class without loading all schemas.",
    properties={
        "query": {
            "type": "string",
            "description": "Keywords or capability to search for (e.g. 'volatility', 'order flow', 'news', 'yields').",
        },
        "limit": {"type": "integer", "description": "Maximum number of tools to return (default 5)."},
    },
    required=["query"],
)


ADD_JOURNAL_ENTRY_TOOL = _tool(
    name="add_journal_entry",
    description="Add a qualitative trading journal entry with emotional state, lessons learned, and tags.",
    properties={
        "content": {"type": "string", "description": "Journal entry text."},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of tags (e.g. ['FOMO', 'Gold', 'Discipline']).",
        },
        "sentiment": {
            "type": "string",
            "description": "Emotional state (e.g. 'neutral', 'disciplined', 'fomo', 'revenge').",
        },
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


SEARCH_SOCIAL_SENTIMENT = _tool(
    name="search_social_sentiment",
    description="Search real-time financial market sentiment, retail buzz, and breaking trader commentary on Twitter/X, Reddit, or web search.",
    properties={
        "query": {
            "type": "string",
            "description": "Search query or ticker cashtag (e.g. '$XAUUSD', '$BTC', 'Federal Reserve').",
        },
        "limit": {"type": "integer", "description": "Maximum number of sentiment items to return (default: 10)."},
    },
    required=["query"],
)


__all__ = [
    "GET_MARKET_CORRELATIONS",
    "GET_RECENT_ACTIVITY",
    "GET_CONVERSATION_HISTORY",
    "WEB_SEARCH",
    "READ_URL",
    "SEARCH_ACADEMIC",
    "SAVE_MARKET_INTELLIGENCE",
    "LIST_ACTIVE_INTELLIGENCE",
    "ARCHIVE_MARKET_INTELLIGENCE",
    "GET_RETAIL_SENTIMENT",
    "GET_FOREX_SENTIMENT",
    "GET_FXSSI_SENTIMENT",
    "GET_STRUCTURED_SENTIMENT",
    "UPDATE_SCRATCHPAD",
    "READ_SCRATCHPAD",
    "GET_DEBATE_STATISTICS",
    "GET_REJECTION_HISTORY",
    "GET_MARKET_CHRONICLE",
    "SEARCH_HISTORICAL_MEMORIES",
    "EXPORT_DEBATE_TRANSCRIPTS",
    "SEARCH_TOOLS_TOOL",
    "ADD_JOURNAL_ENTRY_TOOL",
    "GET_JOURNAL_ENTRIES_TOOL",
    "SEARCH_SOCIAL_SENTIMENT",
]
