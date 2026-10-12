"""
Compatibility facade shim for legacy turn_marker.py.
Re-exports from canonical monika.core.primitives.turn_marker.
"""

from __future__ import annotations

import monika.core.primitives.turn_marker as _canonical

from monika.core.primitives.turn_marker import (
    TurnMarker,
    TurnMarkerManager,
    logger,
)

__all__ = ['TurnMarker', 'TurnMarkerManager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
