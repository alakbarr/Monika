# ==============================================================================
# File: analysis/tools/tool_executor.py
# ==============================================================================

"""
Tool Executor Facade: Backward-compatibility entry point for AI Agent tool execution.
Delegates to modular ToolExecutor in analysis.tools.executor and ToolRegistry.
"""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.executor import (
    FACTOR_CONSISTENCY_TOLERANCE,
    FACTOR_POINT_MAP,
    FACTORS_WITH_VARIABLE_WEIGHT,
    get_default_registry,
)
from monika.application.analysis.tools.executor import (
    ToolExecutor as _PrimaryToolExecutor,
)

# Re-export models and types for any downstream code expecting them in tool_executor
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    BondYieldData,
    COTReport,
    DXYData,
    EconomicCalendar,
    FedWatchProbability,
    FundamentalBrief,
    FVGZone,
    InterestRate,
    LiquidityZone,
    MarketChronicle,
    NewsDigest,
    NewsItem,
    OrderBlock,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    RiskState,
    SRZone,
    StructureBreak,
    SwingPoint,
    SystemConfig,
    TechnicalIndicator,
    TelegramConversation,
    TradeTrigger,
    TreasuryYield,
    UserMarketIntel,
    VIXData,
)


class ToolExecutor(_PrimaryToolExecutor):
    """Facade ToolExecutor maintaining full backward compatibility."""

    pass


__all__ = [
    "ToolExecutor",
    "FACTOR_POINT_MAP",
    "FACTOR_CONSISTENCY_TOLERANCE",
    "FACTORS_WITH_VARIABLE_WEIGHT",
    "get_default_registry",
    "clock",
]
