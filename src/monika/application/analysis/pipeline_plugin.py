# ==============================================================================
# File: analysis/pipeline_plugin.py
# ==============================================================================

"""
Analysis Pipeline Plugin Base Interface.
Decouples the complete analysis cycle / trading style into swappable plugins.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from harness.contract import TradingPlugin, PluginCategory, PluginMetadata
from risk.trade_proposal import TradeProposal


class AnalysisPipelinePlugin(TradingPlugin, ABC):
    """
    Abstract Base Class for full Analysis Cycle / Trading Style Plugins.
    Enables users to swap between Macro-to-Asset, Scalping, Pure Quant, etc.
    """
    metadata: PluginMetadata

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "metadata"):
            self.metadata.category = PluginCategory.ANALYSIS_PIPELINE

    @abstractmethod
    async def execute_analysis_cycle(
        self,
        session: AsyncSession,
        asset_universe: List[str],
        forced: bool = False,
        **kwargs
    ) -> List[TradeProposal]:
        """
        Executes a complete market analysis cycle for the given asset universe.
        Returns a list of validated TradeProposal instances ready for RiskGate evaluation.
        """
        pass

    @abstractmethod
    def get_pipeline_telemetry(self) -> Dict[str, Any]:
        """Returns pipeline-specific telemetry and performance metrics for the dashboard."""
        return {}
