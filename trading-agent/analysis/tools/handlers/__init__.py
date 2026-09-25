"""
Modular tool handlers package with decorator auto-registration (Phase 5).
Imports all legacy and modular handler submodules to trigger registration into default_tool_registry.
"""

from analysis.tools.handlers import (
    market_data,
    macro_data,
    sentiment_data,
    position_mgmt,
    trade_intel,
    system_info,
    analysis_submit,
    scratchpad,
    intelligence,
    timesfm,
    phase_transition,
    category_loader,
    verified_snapshot,
    # Phase 5 modular handlers
    market_data_tools,
    macro_tools,
    sentiment_tools,
    news_tools,
    trading_tools,
    smc_tools,
    db_tools,
    ptc_handler,
    skills_tools,
    pattern_similarity_tools,
)
from analysis.tools.domain import spill_reader_tool

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
    "skills_tools",
    "pattern_similarity_tools",
]
