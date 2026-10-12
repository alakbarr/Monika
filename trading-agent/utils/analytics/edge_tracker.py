"""
Compatibility facade shim for legacy edge_tracker.py.
Re-exports from canonical monika.core.analytics.edge_tracker.
"""

from __future__ import annotations

import monika.core.analytics.edge_tracker as _canonical

from monika.core.analytics.edge_tracker import (
    binomial_confidence_interval,
    is_trade_win,
    compute_edge_status,
)

__all__ = ['binomial_confidence_interval', 'is_trade_win', 'compute_edge_status']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
