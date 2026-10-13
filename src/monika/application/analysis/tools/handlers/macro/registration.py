# ==============================================================================
# File: analysis/tools/handlers/macro/registration.py
# ==============================================================================

"""
Tool registration for macroeconomic tool handlers into ToolRegistry.
"""

from typing import Optional

from monika.application.analysis.tools.handlers.macro.calendar import (
    handle_get_earnings_calendar,
    handle_get_economic_calendar,
    handle_get_economic_surprise,
    handle_get_indonesia_macro,
    handle_get_surprise_summary,
    handle_inspect_economic_report,
)
from monika.application.analysis.tools.handlers.macro.central_banks import (
    handle_diff_central_bank_documents,
    handle_get_central_bank_expectations,
    handle_get_ecb_qt_progress,
    handle_get_fed_net_liquidity_and_stress,
    handle_get_fedwatch_probabilities,
    handle_get_g10_macro_divergence,
    handle_get_global_pmi_trend,
    handle_get_interest_rates,
    handle_get_macro_cross_report_synthesis,
)
from monika.application.analysis.tools.handlers.macro.fixed_income import (
    handle_get_bond_yield_spreads,
    handle_get_treasury_auction_results,
    handle_get_treasury_yields,
)
from monika.application.analysis.tools.handlers.macro.regime import (
    handle_get_macro_bias_score,
    handle_get_market_regime,
    handle_get_market_session,
    handle_get_volatility_regime,
)
from monika.application.analysis.tools.handlers.macro.sentiment_commodities import (
    handle_get_cot_report,
    handle_get_dxy,
    handle_get_eia_oil_inventory,
    handle_get_fear_greed_index,
    handle_get_funding_rate,
    handle_get_macro_priced_in_score,
    handle_get_precomputed_cot_signals,
    handle_get_vix,
    handle_get_weekly_macro_summary,
)
from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry


def register_macro_tools(registry: Optional[ToolRegistry] = None):
    registry = registry or ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_market_session",
            description="Fetch currently open market sessions (London, New York, Tokyo, Sydney) and high-volatility overlaps.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_market_session,
            toolset="macro",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_volatility_regime",
            description="Fetch current volatility regime from ATR/VIX ratios.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_volatility_regime,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_macro_bias_score",
            description="Fetch normalized macroeconomic bias score for a currency pair.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_macro_bias_score,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_macro_priced_in_score",
            description="Calculate macroeconomic priced-in score and saturation analysis using COT percentiles, retail sentiment, FedWatch probabilities, and ATR run-ups.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Currency pair or asset (e.g. EURUSD, USDJPY, XAUUSD)"},
                    "cot_percentile": {"type": "number", "description": "COT positioning percentile (0-100)"},
                    "retail_sentiment": {"type": "number", "description": "Retail long percentage (0-100)"},
                    "fedwatch_dominant_prob": {
                        "type": "number",
                        "description": "Dominant rate outcome probability (0-100)",
                    },
                    "eurusd_run_up_vs_atr": {"type": "number", "description": "Recent move extension relative to ATR"},
                    "fedwatch_repricing_delta": {"type": "number", "description": "FedWatch shift percentage delta"},
                },
            },
            handler=handle_get_macro_priced_in_score,
            toolset="macro",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_dxy",
            description="Fetch US Dollar Index (DXY) price, daily change, and trend direction.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_dxy,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_vix",
            description="Fetch CBOE Volatility Index (VIX) and regime classification.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_vix,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_funding_rate",
            description="Fetch perpetual futures funding rate for crypto assets (BTCUSD).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_funding_rate,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fear_greed_index",
            description="Fetch Crypto Fear & Greed sentiment index.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_fear_greed_index,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_eia_oil_inventory",
            description="Fetch EIA crude oil inventories weekly report data.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_eia_oil_inventory,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fedwatch_probabilities",
            description="Fetch CME FedWatch interest rate meeting target probabilities.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}}},
            handler=handle_get_fedwatch_probabilities,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_central_bank_expectations",
            description="Fetch market-implied rate decision expectations (probabilities of Rate Hike, Hold, Rate Cut) across FED, ECB, BOE, BOJ, RBA.",
            parameters={"type": "object", "properties": {"bank": {"type": "string"}}},
            handler=handle_get_central_bank_expectations,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_market_regime",
            description="Fetch full market regime classification including HMM, trend, and volatility state.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_market_regime,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_treasury_yields",
            description="Fetch US Treasury yield curve (2Y, 5Y, 10Y, 30Y) and inversion status.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_treasury_yields,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_bond_yield_spreads",
            description="Fetch international 10Y sovereign bond yield spreads vs US 10Y.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_bond_yield_spreads,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_cot_report",
            description="Fetch CFTC Commitments of Traders (COT) institutional positioning.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "market_codes": {"type": "array"}},
            },
            handler=handle_get_cot_report,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_economic_calendar",
            description="Fetch high and medium impact economic events from the calendar.",
            parameters={
                "type": "object",
                "properties": {"hours_back": {"type": "integer"}, "hours_ahead": {"type": "integer"}},
            },
            handler=handle_get_economic_calendar,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_weekly_macro_summary",
            description="Generate a comprehensive weekly macroeconomic summary covering key high-impact events, DXY, VIX, FedWatch, and yields.",
            parameters={
                "type": "object",
                "properties": {"days_ahead": {"type": "integer"}, "currencies": {"type": "string"}},
            },
            handler=handle_get_weekly_macro_summary,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_economic_surprise",
            description="Fetch historical economic data surprise scores.",
            parameters={
                "type": "object",
                "properties": {"currency": {"type": "string"}, "days_back": {"type": "integer"}},
            },
            handler=handle_get_economic_surprise,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_interest_rates",
            description="Fetch central bank policy interest rates (Fed, ECB, BOE, BOJ, RBA).",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_interest_rates,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_precomputed_cot_signals",
            description="Fetch pre-computed COT signals showing institutional positioning and sentiment flags.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_precomputed_cot_signals,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_surprise_summary",
            description="Fetch aggregated economic surprise scores per currency for the last 2 weeks.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_surprise_summary,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="inspect_economic_report",
            description="Decompose macroeconomic reports (CPI, NFP, PCE, PPI, JOLTS, ISM) into granular sub-components, identifying top upside/downside drivers, noise vs structural persistence, and labor quality.",
            parameters={
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "description": "CPI, NFP, PCE, PPI, JOLTS, ISM_MANUFACTURING, ISM_SERVICES, UMICH",
                    },
                    "period": {"type": "string", "description": "Period string e.g. 2026-09"},
                    "country": {"type": "string", "description": "US, EU, UK, JP"},
                    "currency": {"type": "string", "description": "USD, EUR, GBP, JPY"},
                },
            },
            handler=handle_inspect_economic_report,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="diff_central_bank_documents",
            description="Perform sentence-level redline diffing between consecutive central bank monetary statements and minutes (Fed, ECB, BoE, BoJ), calculating net monetary policy tone shift (-1.0 to +1.0).",
            parameters={
                "type": "object",
                "properties": {
                    "bank": {"type": "string", "description": "FED, ECB, BOE, BOJ"},
                    "doc_type": {"type": "string", "description": "MINUTES, STATEMENT, BEIGE_BOOK"},
                },
            },
            handler=handle_diff_central_bank_documents,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_macro_cross_report_synthesis",
            description="Synthesize the complete macroeconomic pipeline: ISM Prices Paid -> PPI -> CPI -> Core PCE -> Wage Growth -> Fed Rate Reaction & DXY direction.",
            parameters={
                "type": "object",
                "properties": {
                    "currency": {"type": "string", "description": "Currency code e.g. USD"},
                    "lookback_days": {"type": "integer", "description": "Days of lookback"},
                },
            },
            handler=handle_get_macro_cross_report_synthesis,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_g10_macro_divergence",
            description="Evaluate relative macroeconomic divergence, interest rate differentials, and growth momentum between G10 currencies (EURUSD, USDJPY, GBPUSD, AUDUSD).",
            parameters={
                "type": "object",
                "properties": {
                    "pair": {"type": "string", "description": "Currency pair symbol e.g. EURUSD, USDJPY"},
                },
            },
            handler=handle_get_g10_macro_divergence,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fed_net_liquidity_and_stress",
            description="Fetch Federal Reserve weekly Net Liquidity (WALCL - TGA - RRP), corporate credit spreads (HY OAS), and interbank funding stress (SOFR).",
            parameters={
                "type": "object",
                "properties": {
                    "lookback_weeks": {"type": "integer", "description": "Weeks to evaluate"},
                },
            },
            handler=handle_get_fed_net_liquidity_and_stress,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_treasury_auction_results",
            description="Inspect US Treasury debt auction outcomes (2Y, 5Y, 10Y, 30Y) including auction tail in basis points, bid-to-cover ratio, and foreign indirect demand.",
            parameters={
                "type": "object",
                "properties": {
                    "tenor": {"type": "string", "description": "2Y, 5Y, 10Y, 30Y"},
                    "limit": {"type": "integer", "description": "Number of auctions"},
                },
            },
            handler=handle_get_treasury_auction_results,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_indonesia_macro",
            description="Fetch Indonesian macro indicators: Bank Indonesia BI-Rate, JISDOR USD/IDR, BPS Headline Inflation YoY/MoM, and Trade Balance.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_indonesia_macro,
            toolset="macro",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_earnings_calendar",
            description="Fetch upcoming corporate earnings releases, EPS estimates, and earnings dates for stocks (NASDAQ, S&P 500).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                },
            },
            handler=handle_get_earnings_calendar,
            toolset="macro",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_ecb_qt_progress",
            description="Track European Central Bank (ECB) balance sheet reduction, Quantitative Tightening (QT) progress, APP passive runoff, and PEPP reinvestment phase-out.",
            parameters={
                "type": "object",
                "properties": {
                    "lookback_weeks": {"type": "integer", "description": "Weeks to evaluate (default 8)"},
                },
            },
            handler=handle_get_ecb_qt_progress,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_global_pmi_trend",
            description="Track global and regional manufacturing PMIs (JPMorgan Global, US, Eurozone, UK, China Caixin), expansion vs contraction regime, and regional divergence.",
            parameters={
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Period e.g. '2026-09' (optional)"},
                },
            },
            handler=handle_get_global_pmi_trend,
            toolset="macro",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)
