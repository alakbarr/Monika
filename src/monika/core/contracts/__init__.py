# ==============================================================================
# File: core/contracts/__init__.py
# ==============================================================================

"""Core architectural contracts, protocols, and plugin definitions."""

from monika.core.contracts.plugin import (
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
    "EventBusProtocol",
    "PluginCategory",
    "PluginMetadata",
    "PluginOrigin",
    "PluginState",
    "ServiceContainerProtocol",
    "TaskRegistryProtocol",
    "TradingPlugin",
]
