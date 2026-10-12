"""
Compatibility facade shim for legacy clock.py.
Re-exports from canonical monika.core.primitives.clock.
"""

from __future__ import annotations

import monika.core.primitives.clock as _canonical

from monika.core.primitives.clock import (
    async_frozen_time,
    ensure_utc,
    frozen_time,
    get_simulated_now,
    is_simulated,
    now,
    set_simulated_now,
    utc_now_iso,
)

__all__ = ['async_frozen_time', 'ensure_utc', 'frozen_time', 'get_simulated_now', 'is_simulated', 'now', 'set_simulated_now', 'utc_now_iso']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
