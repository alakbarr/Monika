"""
Compatibility facade shim for legacy container.py.
Re-exports from canonical monika.infrastructure.infra.container.
"""

from __future__ import annotations

import monika.infrastructure.infra.container as _canonical

from monika.infrastructure.infra.container import (
    ServiceContainer,
    T,
    get_container,
)

__all__ = ['ServiceContainer', 'T', 'get_container']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
