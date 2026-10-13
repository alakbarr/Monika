# ==============================================================================
# File: analysis/tools/handlers/macro_tools.py
# ==============================================================================

"""
Backward-compatible facade for macroeconomic analysis tool handlers.
All implementations have been refactored into `monika.application.analysis.tools.handlers.macro.*`.
"""

import sys
import types
from typing import Any

import monika.application.analysis.tools.handlers.macro as _macro_pkg
from monika.application.analysis.tools.handlers.macro import (
    _extract_fedwatch_action_probs,
    _get_macro_context,
    _parse_iso_or_str_dt,
    _safe_execute,
    base as _base_mod,
    calendar as _calendar_mod,
    central_banks as _central_banks_mod,
    fixed_income as _fixed_income_mod,
    handle_diff_central_bank_documents,
    handle_get_bond_yield_spreads,
    handle_get_central_bank_expectations,
    handle_get_cot_report,
    handle_get_dxy,
    handle_get_earnings_calendar,
    handle_get_ecb_qt_progress,
    handle_get_economic_calendar,
    handle_get_economic_surprise,
    handle_get_eia_oil_inventory,
    handle_get_fear_greed_index,
    handle_get_fed_net_liquidity_and_stress,
    handle_get_fedwatch_probabilities,
    handle_get_funding_rate,
    handle_get_g10_macro_divergence,
    handle_get_global_pmi_trend,
    handle_get_indonesia_macro,
    handle_get_interest_rates,
    handle_get_macro_bias_score,
    handle_get_macro_cross_report_synthesis,
    handle_get_macro_priced_in_score,
    handle_get_market_regime,
    handle_get_market_session,
    handle_get_precomputed_cot_signals,
    handle_get_surprise_summary,
    handle_get_treasury_auction_results,
    handle_get_treasury_yields,
    handle_get_vix,
    handle_get_volatility_regime,
    handle_get_weekly_macro_summary,
    handle_inspect_economic_report,
    logger,
    regime as _regime_mod,
    register_macro_tools,
    registration as _registration_mod,
    sentiment_commodities as _sentiment_commodities_mod,
)

# Automatic tool registration on import (preserved from original monolith)
register_macro_tools()

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


class _MacroToolsFacadeModule(types.ModuleType):
    """Module proxy forwarding attribute mutations to submodules for transparent monkeypatching."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for submodule in (
            _macro_pkg,
            _base_mod,
            _regime_mod,
            _calendar_mod,
            _fixed_income_mod,
            _central_banks_mod,
            _sentiment_commodities_mod,
            _registration_mod,
        ):
            if hasattr(submodule, name):
                setattr(submodule, name, value)


_current_mod = sys.modules[__name__]
_proxy_mod = _MacroToolsFacadeModule(__name__, __doc__)
_proxy_mod.__dict__.update(_current_mod.__dict__)
sys.modules[__name__] = _proxy_mod
