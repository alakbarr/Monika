# ==============================================================================
# File: analysis/tools/handlers/phase_transition.py
# ==============================================================================

"""
Phase transition tool handler: explicit analysis phase advancement.
Direct execution without circular trampolines.
"""

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


async def handle_transition_analysis_phase(args: dict, **kwargs) -> dict:
    target_phase = int(args.get("target_phase", 2))
    rationale = args.get("rationale", "")
    return {
        "status": "success",
        "target_phase": target_phase,
        "rationale": rationale,
        "message": f"Phase transition to Phase {target_phase} acknowledged. Unlocking phase tools.",
    }


@register_tool("transition_analysis_phase", aliases=["transition_phase"], category="GENERAL", parallel_safe=False)
class TransitionAnalysisPhaseHandler(ToolHandler):
    name = "transition_analysis_phase"
    category = "GENERAL"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_transition_analysis_phase(args, **kwargs)
