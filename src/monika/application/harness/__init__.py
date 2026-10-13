"""
Backward-compatibility facade for Plugin Microkernel Harness.
Canonical location: monika.application.plugins.engine
"""

import sys
import monika.application.plugins.engine as _canonical

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

sys.modules[__name__] = _canonical
