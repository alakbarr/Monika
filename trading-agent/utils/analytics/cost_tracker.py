"""
Compatibility facade shim for legacy cost_tracker.py.
Re-exports from canonical monika.core.analytics.cost_tracker.
"""

from __future__ import annotations

import monika.core.analytics.cost_tracker as _canonical

from monika.core.analytics.cost_tracker import (
    CostTracker,
)

__all__ = ['CostTracker']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
