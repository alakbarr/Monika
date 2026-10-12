"""
Compatibility facade shim for legacy context_snapshot.py.
Re-exports from canonical monika.application.protocol.context_snapshot.
"""

from __future__ import annotations

import monika.application.protocol.context_snapshot as _canonical

from monika.application.protocol.context_snapshot import (
    compute_context_snapshot_id,
    detect_context_version_split,
)

__all__ = ['compute_context_snapshot_id', 'detect_context_version_split']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
