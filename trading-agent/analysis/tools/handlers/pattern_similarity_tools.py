# ==============================================================================
# File: analysis/tools/handlers/pattern_similarity_tools.py
# ==============================================================================

"""
Tool handler for historical chart pattern similarity screening.
Enables Stage 2 LLM to query historical chart similarity on-demand.
"""

import logging
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool

logger = logging.getLogger("TradingAgent.ToolHandlers.PatternSimilarity")


@register_tool(
    "scan_pattern_similarity",
    aliases=["get_pattern_similarity", "screen_chart_patterns"],
    category="TECHNICAL",
    parallel_safe=True,
)
class ScanPatternSimilarityHandler(ToolHandler):
    """
    Scans historical data for chart patterns similar to the current pattern,
    evaluating macroeconomic context and historical forward outcomes.
    """
    name = "scan_pattern_similarity"
    category = "TECHNICAL"
    parallel_safe = True

    async def execute(
        self,
        args: Dict[str, Any],
        session: AsyncSession,
        executor: Any = None,
        **kwargs: Any,
    ) -> str:
        symbol = args.get("symbol")
        if not symbol:
            return "Error: 'symbol' parameter is required."

        timeframes = args.get("timeframes", ["D1", "H4", "H1"])
        if isinstance(timeframes, str):
            timeframes = [t.strip() for t in timeframes.split(",")]

        try:
            from indicators.pattern_similarity import PatternSimilarityEngine

            settings = getattr(executor, "settings", {}) or {}
            engine = PatternSimilarityEngine(session=session, settings=settings)

            result = await engine.screen(symbol=symbol, timeframes=timeframes)
            return result.format_for_prompt()
        except Exception as e:
            logger.error(f"Error in scan_pattern_similarity for {symbol}: {e}", exc_info=True)
            return f"Error executing pattern similarity scan for {symbol}: {str(e)}"
