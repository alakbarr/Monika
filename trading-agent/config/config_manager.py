"""
Compatibility facade shim for legacy config_manager.py.
Re-exports from canonical monika.core.config.config_manager.
"""

from __future__ import annotations

import monika.core.config.config_manager as _canonical

from monika.core.config.config_manager import (
    ConfigManager,
    logger,
)

__all__ = ['ConfigManager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
