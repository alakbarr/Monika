# ==============================================================================
# File: analysis/tools/handlers/scratchpad.py
# ==============================================================================

"""
Scratchpad tool handlers: working memory anchors for intermediate calculations.
Direct execution without circular trampolines.
"""

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from analysis.memory.working_scratchpad import WorkingScratchpad


def _resolve_symbol(args: dict, executor: Optional[Any] = None) -> str:
    if executor and hasattr(executor, "_resolve_symbol"):
        resolved = executor._resolve_symbol(args)
        if resolved:
            return resolved
    return args.get("symbol") or getattr(executor, "symbol", None) or "DEFAULT"


async def handle_update_scratchpad(args: dict, executor: Optional[Any] = None, **kwargs) -> dict:
    symbol = _resolve_symbol(args, executor)
    updated = WorkingScratchpad.update_scratchpad(symbol, args)
    summary = WorkingScratchpad.get_summary_text(symbol)
    return {
        "status": "success",
        "message": f"Scratchpad for {symbol} updated successfully.",
        "summary": summary,
        "scratchpad": updated,
    }


async def handle_read_scratchpad(args: dict, executor: Optional[Any] = None, **kwargs) -> dict:
    symbol = _resolve_symbol(args, executor)
    state = WorkingScratchpad.read_scratchpad(symbol)
    summary = WorkingScratchpad.get_summary_text(symbol)
    return {
        "status": "success",
        "symbol": symbol,
        "summary": summary,
        "scratchpad": state,
    }


@register_tool("update_scratchpad", aliases=["write_scratchpad"], category="GENERAL", parallel_safe=False)
class UpdateScratchpadHandler(ToolHandler):
    name = "update_scratchpad"
    category = "GENERAL"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_update_scratchpad(args, executor=executor, **kwargs)


@register_tool("read_scratchpad", aliases=["get_scratchpad"], category="GENERAL", parallel_safe=True)
class ReadScratchpadHandler(ToolHandler):
    name = "read_scratchpad"
    category = "GENERAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_read_scratchpad(args, executor=executor, **kwargs)
