"""
Compatibility facade shim for legacy extension_loader.py.
Re-exports from canonical monika.application.plugins.manager.extension_loader.
"""

from __future__ import annotations

import monika.application.plugins.manager.extension_loader as _canonical

from monika.application.plugins.manager.extension_loader import (
    load_plugins,
    load_single_plugin,
    teardown_single_plugin,
)

__all__ = ['load_plugins', 'load_single_plugin', 'teardown_single_plugin']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
