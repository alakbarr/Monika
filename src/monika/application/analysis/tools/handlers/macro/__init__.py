# ==============================================================================
# File: analysis/tools/handlers/macro/__init__.py
# ==============================================================================

"""
Macroeconomic analysis tools subpackage.
Provides market sessions, interest rates, central bank analysis, bond yields,
COT reports, economic calendars, sentiment indices, and commodity inventories.
"""

from monika.application.analysis.tools.handlers.macro.base import (
    _get_macro_context,
    _safe_execute,
    logger,
)
from monika.application.analysis.tools.handlers.macro.calendar import (
    handle_get_earnings_calendar,
    handle_get_economic_calendar,
    handle_get_economic_surprise,
    handle_get_indonesia_macro,
    handle_get_surprise_summary,
    handle_inspect_economic_report,
)
from monika.application.analysis.tools.handlers.macro.central_banks import (
    _extract_fedwatch_action_probs,
    _parse_iso_or_str_dt,
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
from monika.application.analysis.tools.handlers.macro.registration import (
    register_macro_tools,
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

__all__ = [
    "_get_macro_context",
    "_safe_execute",
    "logger",
    "handle_get_market_session",
    "handle_get_volatility_regime",
    "handle_get_macro_bias_score",
    "handle_get_market_regime",
    "handle_get_economic_calendar",
    "handle_get_economic_surprise",
    "handle_get_surprise_summary",
    "handle_get_earnings_calendar",
    "handle_get_indonesia_macro",
    "handle_inspect_economic_report",
    "handle_get_treasury_yields",
    "handle_get_bond_yield_spreads",
    "handle_get_treasury_auction_results",
    "_parse_iso_or_str_dt",
    "_extract_fedwatch_action_probs",
    "handle_get_interest_rates",
    "handle_get_central_bank_expectations",
    "handle_get_fedwatch_probabilities",
    "handle_diff_central_bank_documents",
    "handle_get_macro_cross_report_synthesis",
    "handle_get_g10_macro_divergence",
    "handle_get_fed_net_liquidity_and_stress",
    "handle_get_ecb_qt_progress",
    "handle_get_global_pmi_trend",
    "handle_get_precomputed_cot_signals",
    "handle_get_cot_report",
    "handle_get_vix",
    "handle_get_funding_rate",
    "handle_get_fear_greed_index",
    "handle_get_eia_oil_inventory",
    "handle_get_dxy",
    "handle_get_weekly_macro_summary",
    "handle_get_macro_priced_in_score",
    "register_macro_tools",
]
