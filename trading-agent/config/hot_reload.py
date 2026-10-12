"""
Compatibility facade shim for legacy hot_reload.py.
Re-exports from canonical monika.core.config.hot_reload.
"""

from __future__ import annotations

import monika.core.config.hot_reload as _canonical

from monika.core.config.hot_reload import (
    AtomicConfigWriter,
    ConfigReloader,
    RiskParameterReloader,
    logger,
)

__all__ = ['AtomicConfigWriter', 'ConfigReloader', 'RiskParameterReloader', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
