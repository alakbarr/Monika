"""
Compatibility facade shim for legacy trace_search.py.
Re-exports from canonical monika.interfaces.dashboard.routes.trace_search.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.trace_search as _canonical

from monika.interfaces.dashboard.routes.trace_search import (
    logger,
    search_traces,
    slow_llm_calls,
    trace_search_router,
)

__all__ = ['logger', 'search_traces', 'slow_llm_calls', 'trace_search_router']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
