"""
Compatibility facade shim for legacy event_loop.py.
Re-exports from canonical monika.infrastructure.infra.event_loop.
"""

from __future__ import annotations

import monika.infrastructure.infra.event_loop as _canonical

from monika.infrastructure.infra.event_loop import (
    get_loop_factory,
    run_async,
)

__all__ = ['get_loop_factory', 'run_async']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
