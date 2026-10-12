"""
Compatibility facade shim for legacy direction.py.
Re-exports from canonical monika.domain.market.direction.
"""

from __future__ import annotations

import monika.domain.market.direction as _canonical

from monika.domain.market.direction import (
    is_valid_direction,
    normalize_direction,
)

__all__ = ['is_valid_direction', 'normalize_direction']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
