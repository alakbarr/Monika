# ==============================================================================
# File: analysis/tools/handlers/market_data.py
# ==============================================================================

import json
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


@register_tool("get_market_quote", aliases=["market_quote", "get_quote", "fetch_quote", "quote"], category="TECHNICAL", parallel_safe=True)
class GetMarketQuoteHandler(ToolHandler):
    name = "get_market_quote"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.handlers.market_data_tools import handle_get_market_quote
        return await handle_get_market_quote(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_price_data", aliases=["get_prices", "fetch_price", "fetch_prices"], category="TECHNICAL", parallel_safe=True)
class GetPriceDataHandler(ToolHandler):
    name = "get_price_data"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.composite_tools import execute_price_data
        target_executor = executor or getattr(self, "executor", None)
        return await execute_price_data(
            target_executor,
            args.get("symbol", ""),
            direction=args.get("direction"),
            entry_price=args.get("entry_price")
        )


@register_tool("get_technical_analysis", aliases=["technical_analysis", "get_ta"], category="TECHNICAL", parallel_safe=True)
class GetTechnicalAnalysisHandler(ToolHandler):
    name = "get_technical_analysis"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.composite_tools import execute_technical_analysis
        target_executor = executor or getattr(self, "executor", None)
        return await execute_technical_analysis(
            target_executor,
            args.get("symbol", ""),
            timeframes=args.get("timeframes")
        )


@register_tool("get_chart", aliases=["fetch_chart", "show_chart"], category="TECHNICAL", parallel_safe=True)
class GetChartHandler(ToolHandler):
    name = "get_chart"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.handlers.market_data_tools import handle_get_chart
        return await handle_get_chart(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_multi_timeframe_summary", aliases=["mtf_summary", "get_mtf"], category="TECHNICAL", parallel_safe=True)
class GetMultiTimeframeSummaryHandler(ToolHandler):
    name = "get_multi_timeframe_summary"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.handlers.market_data_tools import handle_get_multi_timeframe_summary
        return await handle_get_multi_timeframe_summary(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_spread_snapshot", aliases=["get_spread", "spread_snapshot"], category="TECHNICAL", parallel_safe=True)
class GetSpreadSnapshotHandler(ToolHandler):
    name = "get_spread_snapshot"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.handlers.market_data_tools import handle_get_spread_snapshot
        return await handle_get_spread_snapshot(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_price_history", aliases=["price_history"], category="TECHNICAL", parallel_safe=True)
class GetPriceHistoryHandler(ToolHandler):
    name = "get_price_history"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.handlers.market_data_tools import handle_get_price_history
        return await handle_get_price_history(args, session=session, executor=executor, settings=self.settings)


@register_tool("get_technical_indicators", aliases=["get_technical_indicator"], category="TECHNICAL", parallel_safe=True)
class GetTechnicalIndicatorsHandler(ToolHandler):
    name = "get_technical_indicators"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        from analysis.tools.handlers.market_data_tools import handle_get_technical_indicators
        return await handle_get_technical_indicators(args, session=session, executor=executor, settings=self.settings)

