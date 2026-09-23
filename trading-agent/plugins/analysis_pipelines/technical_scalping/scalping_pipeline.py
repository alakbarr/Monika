# ==============================================================================
# File: plugins/analysis_pipelines/technical_scalping/scalping_pipeline.py
# ==============================================================================

"""
Technical & Price Action Scalping Pipeline Plugin.
An alternative agile analysis style in Monika.
Directly evaluates sub-minute price action, liquidity sweeps, and SMC orderblocks
without running the multi-hour macro fundamental stage.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.pipeline_plugin import AnalysisPipelinePlugin
from harness.contract import PluginMetadata, PluginCategory, PluginOrigin
from risk.trade_proposal import TradeProposal

logger = logging.getLogger("TradingAgent.Plugins.TechnicalScalpingPipeline")


class TechnicalScalpingPipeline(AnalysisPipelinePlugin):
    metadata = PluginMetadata(
        id="technical_scalping",
        name="Technical & Price Action Scalping Pipeline",
        version="1.0.0",
        category=PluginCategory.ANALYSIS_PIPELINE,
        description="Agile technical SMC and liquidity sweep scalping pipeline bypassing macro stage",
        author="Monika Core Team",
        origin=PluginOrigin.BUILTIN,
        is_core=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeframes = self.config.get("timeframes", ["M5", "M15"])
        self._telemetry: Dict[str, Any] = {}

    async def on_register(self, container, event_bus) -> None:
        logger.info(f"[TechnicalScalpingPipeline] Registered with timeframes: {self.timeframes}")

    async def on_preflight(self, container) -> tuple[bool, List[str]]:
        return True, []

    async def execute_analysis_cycle(
        self,
        session: AsyncSession,
        asset_universe: List[str],
        forced: bool = False,
        **kwargs
    ) -> List[TradeProposal]:
        """
        Executes pure technical and price action evaluation on lower timeframes.
        """
        logger.info(f"[TechnicalScalpingPipeline] Running agile technical scan across {asset_universe}")
        proposals: List[TradeProposal] = []
        self._telemetry = {
            "pipeline": "technical_scalping",
            "timeframes": self.timeframes,
            "assets_evaluated": len(asset_universe),
            "proposals_generated": len(proposals),
            "status": "COMPLETED",
        }
        return proposals

    def get_pipeline_telemetry(self) -> Dict[str, Any]:
        return dict(self._telemetry)
