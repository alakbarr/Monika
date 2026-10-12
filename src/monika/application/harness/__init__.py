# ==============================================================================
# File: harness/__init__.py
# ==============================================================================

"""
Monika Trading Harness Core.
Provides microkernel architecture, universal plugin contracts, and topological engine.
"""

from monika.application.harness.contract import (
    PluginCategory,
    PluginOrigin,
    PluginMetadata,
    PluginState,
    TradingPlugin,
    TaskRegistryProtocol,
    EventBusProtocol,
    ServiceContainerProtocol,
)
from monika.application.harness.engine import PluginEngine

__all__ = [
    "PluginCategory",
    "PluginOrigin",
    "PluginMetadata",
    "PluginState",
    "TradingPlugin",
    "TaskRegistryProtocol",
    "EventBusProtocol",
    "ServiceContainerProtocol",
    "PluginEngine",
]
