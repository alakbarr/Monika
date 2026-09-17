import os
import ast

def main():
    src_path = "trading-agent/analysis/tools/tool_executor.py"
    dst_executor_path = "trading-agent/analysis/tools/executor.py"
    dst_facade_path = "trading-agent/analysis/tools/tool_executor.py"

    with open(src_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    header = '''# ==============================================================================
# File: analysis/tools/executor.py
# ==============================================================================

"""
Core Tool Executor: Primary engine for routing and executing AI Agent tools.
Integrates decorator-based ToolRegistry, domain handlers, dynamic tool dispatch,
monotonic guards, LFSP condensation, and OpenTelemetry tracing.
"""

from typing import Any, Dict, Optional, Set
import json
import logging
from pydantic import ValidationError
from analysis.schemas.schemas import SubmitFundamentalBriefSchema, SubmitAssetAnalysisSchema
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, desc, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    NewsItem, EconomicCalendar, TreasuryYield, InterestRate,
    FedWatchProbability, COTReport, VIXData, PriceOHLCV,
    TechnicalIndicator, SwingPoint, SRZone, LiquidityZone, FVGZone,
    FundamentalBrief, AssetAnalysis, TradeTrigger, Position,
    ActivityLog, RiskState, TelegramConversation, OrderBlock, StructureBreak, SystemConfig,
    DXYData, NewsDigest, PaperTradeRecord, BondYieldData,
    UserMarketIntel, MarketChronicle
)

import utils.clock as clock
from analysis.tools.registry import default_tool_registry, ToolRegistry
import analysis.tools.handlers  # Auto-registers all modular tool handlers

logger = logging.getLogger("TradingAgent.ToolExecutor")

FACTOR_POINT_MAP = {
    'fundamental_bias': 2, 'dxy_confirms': 1, 'd1_trend': 2, 'rsi_neutral': 1,
    'near_fvg': 2, 'near_order_block': 2, 'in_ote_zone': 1, 'near_sr_zone': 1,
    'cot_aligned': 1, 'vix_ok': 1, 'liquidity_sweep_confirmed': 2,
    'session_prime': 1,       # modifier tambahan, bukan bagian base-14
    'post_event_entry': 0,    # informational tag, tidak menambah skor
}
FACTOR_CONSISTENCY_TOLERANCE = 1
FACTORS_WITH_VARIABLE_WEIGHT = {'cot_aligned'}


def get_default_registry() -> ToolRegistry:
    return default_tool_registry

'''

    # Extract sections from tool_executor.py
    # Lines 45 to 546: ToolExecutor class up through _tool_transition_analysis_phase
    part1 = "".join(lines[44:546])

    # Dynamic __getattr__
    getattr_snippet = '''
    def __getattr__(self, name: str) -> Any:
        """Dynamic dispatch for _tool_* methods to handlers or execute()."""
        if name.startswith("_tool_"):
            raw_name = name[6:]
            tool_name = self._normalize_tool_name(raw_name) or raw_name

            async def _dynamic_tool_caller(inp: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
                params = {}
                if isinstance(inp, dict):
                    params.update(inp)
                params.update(kwargs)
                return await self.execute(tool_name, params)

            return _dynamic_tool_caller
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
'''

    # Lines 1668 to 2471: validation & fundamental brief submission
    part2 = "".join(lines[1667:2471])

    # Lines 3045 to 3065: _format_smc_data
    part3 = "".join(lines[3044:3065])

    # Lines 3259 to 3274: _get_precomputed_data
    part4 = "".join(lines[3258:3274])

    # Lines 3275 to 4692: SMC proximity, TP target, dynamic ATR, manual order validation, submit_asset_analysis
    part5 = "".join(lines[3274:4691])

    # Also make sure execute() in part1 includes OpenTelemetry span if available
    executor_content = header + part1 + getattr_snippet + "\n" + part2 + "\n" + part3 + "\n" + part4 + "\n" + part5 + "\n"

    # Verify AST parses
    ast.parse(executor_content)
    print("executor.py AST parsed successfully!")

    with open(dst_executor_path, "w", encoding="utf-8") as f:
        f.write(executor_content)
    print(f"Written executor.py with {len(executor_content.splitlines())} lines.")

    # Create slim facade for tool_executor.py (<250 lines)
    facade_content = '''# ==============================================================================
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
'''
    with open(dst_facade_path, "w", encoding="utf-8") as f:
        f.write(facade_content)
    print(f"Written tool_executor.py facade with {len(facade_content.splitlines())} lines.")

if __name__ == "__main__":
    main()
