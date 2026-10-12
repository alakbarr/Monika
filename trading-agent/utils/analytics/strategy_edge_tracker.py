"""
Compatibility facade shim for legacy strategy_edge_tracker.py.
Re-exports from canonical monika.core.analytics.strategy_edge_tracker.
"""

from __future__ import annotations

import monika.core.analytics.strategy_edge_tracker as _canonical

from monika.core.analytics.strategy_edge_tracker import (
    apply_disable_flags,
    compute_strategy_pair_stats,
)

__all__ = ['apply_disable_flags', 'compute_strategy_pair_stats']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
