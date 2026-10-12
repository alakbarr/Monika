"""
Compatibility facade shim for legacy content_distiller.py.
Re-exports from canonical monika.core.primitives.content_distiller.
"""

from __future__ import annotations

import monika.core.primitives.content_distiller as _canonical

from monika.core.primitives.content_distiller import (
    ContentDistiller,
    DEFAULT_SPILL_DIR,
    logger,
)

__all__ = ['ContentDistiller', 'DEFAULT_SPILL_DIR', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
