# ==============================================================================
# File: plugin_kernel/__init__.py
# Description: Monika Plugin Kernel — Universal Plugin Architecture
# ==============================================================================

"""
Monika Plugin Kernel — Universal Plugin Architecture.
Provides unified interfaces, lifecycle state machine, dependency injection,
and reactive event dispatching.
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
from monika.application.plugins.engine.installer import (
    get_community_catalog,
    list_all_plugins_status,
    run_pip_install,
    run_pip_uninstall,
    toggle_plugin_state,
    validate_package_spec,
)
from monika.application.plugins.engine.lifecycle import (
    ReplacementCoordinator,
    ReplacementLease,
    get_plugin_storage_dir,
    get_replacement_coordinator,
    safe_dispatch_hook,
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
    "ReplacementCoordinator",
    "ReplacementLease",
    "get_replacement_coordinator",
    "safe_dispatch_hook",
    "get_plugin_storage_dir",
]
