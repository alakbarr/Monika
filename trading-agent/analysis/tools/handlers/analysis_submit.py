# ==============================================================================
# File: analysis/tools/handlers/analysis_submit.py
# ==============================================================================

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


FACTOR_POINT_MAP = {
    'fundamental_bias': 2, 'dxy_confirms': 1, 'd1_trend': 2, 'rsi_neutral': 1,
    'near_fvg': 2, 'near_order_block': 2, 'in_ote_zone': 1, 'near_sr_zone': 1,
    'cot_aligned': 1, 'vix_ok': 1, 'liquidity_sweep_confirmed': 2,
    'session_prime': 1,       # modifier tambahan, bukan bagian base-14
    'post_event_entry': 0,    # informational tag, tidak menambah skor
}
FACTOR_CONSISTENCY_TOLERANCE = 1
FACTORS_WITH_VARIABLE_WEIGHT = {'cot_aligned'}


async def handle_submit_asset_analysis(args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> Any:
    if executor and hasattr(executor, "_tool_submit_asset_analysis"):
        return await executor._tool_submit_asset_analysis(args)
    from analysis.tools.tool_executor import ToolExecutor
    if session:
        ex = ToolExecutor(session=session)
        return await ex._tool_submit_asset_analysis(args)
    return {"error": "Submit asset analysis requires active executor or session context"}


async def handle_submit_fundamental_brief(args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> Any:
    if executor and hasattr(executor, "_tool_submit_fundamental_brief"):
        return await executor._tool_submit_fundamental_brief(args)
    from analysis.tools.tool_executor import ToolExecutor
    if session:
        ex = ToolExecutor(session=session)
        return await ex._tool_submit_fundamental_brief(args)
    return {"error": "Submit fundamental brief requires active executor or session context"}


async def handle_get_fundamental_brief(args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> Any:
    if executor and hasattr(executor, "_tool_get_fundamental_brief"):
        return await executor._tool_get_fundamental_brief(args)
    from analysis.tools.tool_executor import ToolExecutor
    if session:
        ex = ToolExecutor(session=session)
        return await ex._tool_get_fundamental_brief(args)
    return {"error": "Get fundamental brief requires active executor or session context"}


@register_tool("submit_asset_analysis", aliases=["submit_asset", "submit_trade_analysis", "submit_asset_analysis_schema"], category="EXECUTION", parallel_safe=False)
class SubmitAssetAnalysisHandler(ToolHandler):
    name = "submit_asset_analysis"
    category = "EXECUTION"
    parallel_safe = False  # Sequential barrier

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_submit_asset_analysis(args, session=session, executor=executor, **kwargs)


@register_tool("submit_fundamental_brief", aliases=["submit_fundamental", "submit_fundamental_analysis", "submit_fundamental_brief_schema"], category="MACRO", parallel_safe=False)
class SubmitFundamentalBriefHandler(ToolHandler):
    name = "submit_fundamental_brief"
    category = "MACRO"
    parallel_safe = False  # Sequential barrier

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_submit_fundamental_brief(args, session=session, executor=executor, **kwargs)


@register_tool("get_fundamental_brief", aliases=["fetch_fundamental_brief"], category="MACRO", parallel_safe=True)
class GetFundamentalBriefHandler(ToolHandler):
    name = "get_fundamental_brief"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_fundamental_brief(args, session=session, executor=executor, **kwargs)

