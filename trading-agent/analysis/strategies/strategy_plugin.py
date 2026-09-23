# ==============================================================================
# File: analysis/strategies/strategy_plugin.py
# ==============================================================================

"""
Strategy Plugin Specification for Monika Trading Harness (Phase 3c).
Enables swappable quantitative alpha strategies packaged as TradingPlugins.
"""

from abc import ABC, abstractmethod
from typing import Type, Optional, Dict, Any, List
import logging

from harness.contract import TradingPlugin, PluginCategory, PluginMetadata
from analysis.strategies.base_strategy import EdgeStrategy

logger = logging.getLogger("TradingAgent.StrategyPlugin")


class StrategyPlugin(TradingPlugin, ABC):
    """
    Contract for pluggable quantitative alpha strategies in Monika.
    Bridges between the harness plugin lifecycle and the EdgeStrategy execution engine.
    """
    metadata: PluginMetadata

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "metadata"):
            self.metadata.category = PluginCategory.STRATEGY

    @abstractmethod
    def get_strategy_class(self) -> Type[EdgeStrategy]:
        """Return the EdgeStrategy class implemented by this plugin."""
        pass

    def on_register(self, context) -> None:
        """Auto-register the strategy class into StrategyRegistry upon plugin load."""
        super().on_register(context)
        from analysis.strategies.registry import StrategyRegistry
        strat_cls = self.get_strategy_class()
        StrategyRegistry.register(strat_cls)
        logger.info(f"[StrategyPlugin] Registered strategy '{strat_cls.strategy_id}' via plugin '{self.metadata.id}'")


def wrap_strategy_as_plugin(strategy_cls: Type[EdgeStrategy]) -> StrategyPlugin:
    """Convenience factory to wrap an existing EdgeStrategy class into a StrategyPlugin."""
    strat_id = getattr(strategy_cls, "strategy_id", strategy_cls.__name__)

    class _WrappedStrategyPlugin(StrategyPlugin):
        metadata = PluginMetadata(
            id=f"strategy_{strat_id}",
            name=f"Strategy: {strat_id}",
            version="1.0.0",
            category=PluginCategory.STRATEGY,
            description=f"Auto-wrapped quantitative strategy for {strat_id}",
        )

        def get_strategy_class(self) -> Type[EdgeStrategy]:
            return strategy_cls

    return _WrappedStrategyPlugin()
