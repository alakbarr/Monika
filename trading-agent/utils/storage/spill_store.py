"""
Compatibility facade shim for legacy spill_store.py.
Re-exports from canonical monika.infrastructure.storage.spill_store.
"""

from __future__ import annotations

import monika.infrastructure.storage.spill_store as _canonical

from monika.infrastructure.storage.spill_store import (
    DEFAULT_SPILL_DIR,
    SpillStore,
    get_spill_store,
)

__all__ = ['DEFAULT_SPILL_DIR', 'SpillStore', 'get_spill_store']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
