# ==============================================================================
# File: application/plugins/engine/contract.py
# Monika Universal Plugin Contract Facade
# ==============================================================================

"""
Universal Plugin Contract for Monika Trading Harness.
Canonical core definitions live in monika.core.contracts.plugin.
This module re-exports them for application and external plugin backwards-compatibility.
"""

from __future__ import annotations

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
