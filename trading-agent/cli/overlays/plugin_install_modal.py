"""
Compatibility facade shim for legacy plugin_install_modal.py.
Re-exports from canonical monika.interfaces.cli.overlays.plugin_install_modal.
"""

from __future__ import annotations

import monika.interfaces.cli.overlays.plugin_install_modal as _canonical

from monika.interfaces.cli.overlays.plugin_install_modal import (
    PluginInstallModalScreen,
)

__all__ = ['PluginInstallModalScreen']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
