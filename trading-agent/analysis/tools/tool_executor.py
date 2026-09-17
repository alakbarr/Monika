# ==============================================================================
# File: analysis/tools/tool_executor.py
# ==============================================================================

"""
Tool Executor Facade: Backward-compatibility entry point for AI Agent tool execution.
Delegates to modular ToolExecutor in analysis.tools.executor and ToolRegistry.
"""

from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

from analysis.tools.executor import (
    ToolExecutor as _PrimaryToolExecutor,
    FACTOR_POINT_MAP,
    FACTOR_CONSISTENCY_TOLERANCE,
    FACTORS_WITH_VARIABLE_WEIGHT,
    get_default_registry,
)

# Re-export models and types for any downstream code expecting them in tool_executor
from database.models import (
    NewsItem, EconomicCalendar, TreasuryYield, InterestRate,
    FedWatchProbability, COTReport, VIXData, PriceOHLCV,
    TechnicalIndicator, SwingPoint, SRZone, LiquidityZone, FVGZone,
    FundamentalBrief, AssetAnalysis, TradeTrigger, Position,
    ActivityLog, RiskState, TelegramConversation, OrderBlock, StructureBreak, SystemConfig,
    DXYData, NewsDigest, PaperTradeRecord, BondYieldData,
    UserMarketIntel, MarketChronicle
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
