"""
Compatibility facade shim for legacy plugins.py.
Re-exports from canonical monika.interfaces.cli.plugins.
"""

from __future__ import annotations

import monika.interfaces.cli.plugins as _canonical

from monika.interfaces.cli.plugins import (
    cmd_plugin_disable,
    cmd_plugin_enable,
    cmd_plugin_info,
    cmd_plugin_install,
    cmd_plugin_list,
    cmd_plugin_uninstall,
    console,
    handle_plugin_command,
    logger,
)

__all__ = ['cmd_plugin_disable', 'cmd_plugin_enable', 'cmd_plugin_info', 'cmd_plugin_install', 'cmd_plugin_list', 'cmd_plugin_uninstall', 'console', 'handle_plugin_command', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
