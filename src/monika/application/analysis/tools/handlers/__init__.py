"""
Modular tool handlers package with decorator auto-registration (Phase 5).
Imports all legacy and modular handler submodules to trigger registration into default_tool_registry.
"""

from monika.application.analysis.tools import domain
from monika.application.analysis.tools.domain import spill_reader_tool
from monika.application.analysis.tools.handlers import (
    advanced_quant_tools,
    analysis_submit,
    analytical_query_builder,
    behavioral_alert_tool,
    broker_profile_tool,
    category_loader,
    chart_bridge_tools,
    db_tools,
    execution_handlers,
    intelligence,
    macro_data,
    macro_tools,
    market_data,
    # Phase 5 modular handlers
    market_data_tools,
    news_tools,
    pattern_similarity_tools,
    phase_transition,
    position_mgmt,
    ptc_handler,
    scratchpad,
    sentiment_data,
    sentiment_tools,
    skills_tools,
    smc_tools,
    system_info,
    timesfm,
    trade_intel,
    trading_tools,
    verified_snapshot,
)

__all__ = [
    "market_data",
    "macro_data",
    "sentiment_data",
    "position_mgmt",
    "trade_intel",
    "system_info",
    "analysis_submit",
    "scratchpad",
    "intelligence",
    "timesfm",
    "phase_transition",
    "category_loader",
    "verified_snapshot",
    "market_data_tools",
    "macro_tools",
    "sentiment_tools",
    "news_tools",
    "trading_tools",
    "smc_tools",
    "db_tools",
    "execution_handlers",
    "skills_tools",
    "pattern_similarity_tools",
    "analytical_query_builder",
    "behavioral_alert_tool",
    "broker_profile_tool",
]
