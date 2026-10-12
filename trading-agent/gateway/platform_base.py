"""
Compatibility facade shim for legacy platform_base.py.
Re-exports from canonical monika.interfaces.gateway.platform_base.
"""

from __future__ import annotations

import monika.interfaces.gateway.platform_base as _canonical

from monika.interfaces.gateway.platform_base import (
    BasePlatformAdapter,
    logger,
)

__all__ = ['BasePlatformAdapter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
