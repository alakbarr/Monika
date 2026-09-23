# ==============================================================================
# File: plugin_kernel/__init__.py
# Description: Monika Plugin Kernel (Inspired by Cordis / DeepSeek Harness)
# ==============================================================================

"""
Monika Plugin Kernel — Universal Plugin Architecture.
Provides unified interfaces, lifecycle state machine, dependency injection,
and reactive event dispatching.
"""

from harness.contract import (
    TradingPlugin,
    PluginMetadata,
    PluginCategory,
    PluginOrigin,
    PluginState,
    ServiceContainerProtocol,
    EventBusProtocol,
    TaskRegistryProtocol,
)
from harness.engine import PluginEngine, get_plugin_engine
from harness.installer import (
    list_all_plugins_status,
    toggle_plugin_state,
    get_community_catalog,
    run_pip_install,
    run_pip_uninstall,
    validate_package_spec,
)

__all__ = [
    "TradingPlugin",
    "PluginMetadata",
    "PluginCategory",
    "PluginOrigin",
    "PluginState",
    "ServiceContainerProtocol",
    "EventBusProtocol",
    "TaskRegistryProtocol",
    "PluginEngine",
    "get_plugin_engine",
    "list_all_plugins_status",
    "toggle_plugin_state",
    "get_community_catalog",
    "run_pip_install",
    "run_pip_uninstall",
    "validate_package_spec",
]
