"""
Monika Plugin Microkernel Engine.
Provides microkernel architecture, universal plugin contracts, and topological engine.
"""

from monika.application.plugins.engine.contract import (
    EventBusProtocol,
    PluginCategory,
    PluginMetadata,
    PluginOrigin,
    PluginState,
    ServiceContainerProtocol,
    TaskRegistryProtocol,
    TradingPlugin,
)
from monika.application.plugins.engine.engine import PluginEngine, get_plugin_engine

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
    "get_plugin_engine",
]
