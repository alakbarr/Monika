"""
Compatibility facade shim for legacy trade_autopsy.py.
Re-exports from canonical monika.core.analytics.trade_autopsy.
"""

from __future__ import annotations

import monika.core.analytics.trade_autopsy as _canonical

from monika.core.analytics.trade_autopsy import (
    run_trade_autopsy,
    summarize_recent_patterns,
)

__all__ = ['run_trade_autopsy', 'summarize_recent_patterns']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
