"""
Compatibility facade shim for legacy plugins.py.
Re-exports from canonical monika.interfaces.dashboard.routes.plugins.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.plugins as _canonical

from monika.interfaces.dashboard.routes.plugins import (
    PluginInstallRequest,
    PluginToggleRequest,
    PluginUninstallRequest,
    get_plugin_catalog,
    get_plugins,
    install_plugin,
    logger,
    plugins_router,
    router,
    toggle_plugin,
    uninstall_plugin,
)

__all__ = ['PluginInstallRequest', 'PluginToggleRequest', 'PluginUninstallRequest', 'get_plugin_catalog', 'get_plugins', 'install_plugin', 'logger', 'plugins_router', 'router', 'toggle_plugin', 'uninstall_plugin']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
