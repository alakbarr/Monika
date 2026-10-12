"""
Compatibility facade shim for legacy paper_tracker.py.
Re-exports from canonical monika.core.analytics.paper_tracker.
"""

from __future__ import annotations

import monika.core.analytics.paper_tracker as _canonical

from monika.core.analytics.paper_tracker import (
    PaperTracker,
    _group_by_symbol,
    _group_by_symbol_direction,
)

__all__ = ['PaperTracker', '_group_by_symbol', '_group_by_symbol_direction']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
