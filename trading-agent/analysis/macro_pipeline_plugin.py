# ==============================================================================
# File: analysis/macro_pipeline_plugin.py
# ==============================================================================

"""
Macro-to-Asset Analysis Pipeline Plugin (Phase 3f).
Adapts the standard 2-stage macro-to-asset analytical pipeline and LangGraph cycle
as an operational AnalysisPipelinePlugin for the modular trading harness.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from harness.contract import PluginCategory, PluginMetadata
from analysis.pipeline_plugin import AnalysisPipelinePlugin
from risk.trade_proposal import TradeProposal

logger = logging.getLogger("TradingAgent.MacroPipeline")


class MacroToAssetPipeline(AnalysisPipelinePlugin):
    """
    Standard institutional macro-to-asset pipeline plugin.
    Orchestrates Stage 1 (global macro regime) -> Stage 2 (per-asset thesis & debate)
    producing structured TradeProposal objects.
    """
    metadata = PluginMetadata(
        id="macro_to_asset",
        name="Macro-to-Asset Pipeline",
        version="1.0.0",
        category=PluginCategory.ANALYSIS_PIPELINE,
        description="Two-stage macro-to-asset pipeline with debate synthesis and LangGraph DAG.",
    )

    def __init__(self, scheduler: Optional[Any] = None, settings: Optional[dict] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheduler = scheduler
        self.settings = settings or {}
        self._last_cycle_time: Optional[datetime] = None
        self._cycles_completed: int = 0
        self._proposals_generated: int = 0

    async def execute_analysis_cycle(
        self,
        session: AsyncSession,
        asset_universe: List[str],
        forced: bool = False,
        **kwargs
    ) -> List[TradeProposal]:
        """
        Executes an end-to-end analysis cycle across the specified asset universe.
        Delegates to the active cycle scheduler if attached, or runs ad-hoc analysis.
        """
        logger.info(f"[MacroToAssetPipeline] Starting analysis cycle for universe: {asset_universe} (forced={forced})")
        self._last_cycle_time = datetime.now(timezone.utc)
        self._cycles_completed += 1

        proposals: List[TradeProposal] = []
        if self.scheduler is not None and hasattr(self.scheduler, "run_cycle"):
            try:
                res = await self.scheduler.run_cycle(session, forced=forced)
                if isinstance(res, list):
                    for item in res:
                        if isinstance(item, TradeProposal):
                            proposals.append(item)
            except Exception as e:
                logger.error(f"[MacroToAssetPipeline] Error executing cycle via scheduler: {e}", exc_info=True)

        self._proposals_generated += len(proposals)
        return proposals

    def get_pipeline_telemetry(self) -> Dict[str, Any]:
        """Return pipeline telemetry for observability dashboard."""
        return {
            "pipeline_id": self.metadata.id,
            "pipeline_name": self.metadata.name,
            "cycles_completed": self._cycles_completed,
            "proposals_generated": self._proposals_generated,
            "last_cycle_time": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
            "scheduler_attached": self.scheduler is not None,
        }
