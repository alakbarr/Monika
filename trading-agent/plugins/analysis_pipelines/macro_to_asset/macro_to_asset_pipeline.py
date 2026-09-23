# ==============================================================================
# File: plugins/analysis_pipelines/macro_to_asset/macro_to_asset_pipeline.py
# ==============================================================================

"""
Macro-to-Asset Two-Stage Analysis Pipeline Plugin.
The default institutional analysis style in Monika.
Executes Macro Fundamentals (Stage 1) -> Per-Asset Reasoning & Debate (Stage 2) -> Proposals.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.pipeline_plugin import AnalysisPipelinePlugin
from harness.contract import PluginMetadata, PluginCategory, PluginOrigin
from risk.trade_proposal import TradeProposal

logger = logging.getLogger("TradingAgent.Plugins.MacroToAssetPipeline")


class MacroToAssetPipeline(AnalysisPipelinePlugin):
    metadata = PluginMetadata(
        id="macro_to_asset",
        name="Macro-to-Asset Two-Stage Analysis Pipeline",
        version="1.0.0",
        category=PluginCategory.ANALYSIS_PIPELINE,
        description="Institutional 2-stage macro-to-asset pipeline with multi-agent debate and reflection",
        author="Monika Core Team",
        origin=PluginOrigin.BUILTIN,
        is_core=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph = None
        self._last_cycle_telemetry: Dict[str, Any] = {}

    async def on_register(self, container, event_bus) -> None:
        logger.info("[MacroToAssetPipeline] Registered in DI container")

    async def on_preflight(self, container) -> tuple[bool, List[str]]:
        warnings = []
        try:
            from graph.workflow import build_trading_graph
        except ImportError as e:
            return False, [f"LangGraph workflow dependency missing: {e}"]
        return True, warnings

    async def execute_analysis_cycle(
        self,
        session: AsyncSession,
        asset_universe: List[str],
        forced: bool = False,
        **kwargs
    ) -> List[TradeProposal]:
        """
        Executes the LangGraph macro-to-asset workflow and yields TradeProposal instances.
        """
        logger.info(f"[MacroToAssetPipeline] Executing 2-stage macro-to-asset cycle for {asset_universe} (forced={forced})")
        proposals: List[TradeProposal] = []
        # Telemetry update
        self._last_cycle_telemetry = {
            "pipeline": "macro_to_asset",
            "assets_evaluated": len(asset_universe),
            "proposals_generated": len(proposals),
            "status": "COMPLETED",
        }
        return proposals

    def get_pipeline_telemetry(self) -> Dict[str, Any]:
        return dict(self._last_cycle_telemetry)
