"""
Backward-compatibility facade for plugin contracts.
Canonical location: monika.application.plugins.engine.contract
"""

import sys
import monika.application.plugins.engine.contract as _canonical

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

__all__ = [
    "PluginCategory",
    "PluginOrigin",
    "PluginMetadata",
    "PluginState",
    "TradingPlugin",
    "TaskRegistryProtocol",
    "EventBusProtocol",
    "ServiceContainerProtocol",
]

sys.modules[__name__] = _canonical
