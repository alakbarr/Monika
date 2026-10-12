"""
Compatibility facade shim for legacy tokens.py.
Re-exports from canonical monika.interfaces.dashboard.routes.tokens.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.tokens as _canonical

from monika.interfaces.dashboard.routes.tokens import (
    get_context_tracker_metrics,
    get_per_turn_cost_metrics,
    get_tokens_by_cycle,
    get_tokens_by_role,
    get_tokens_by_subsystem,
    get_tokens_by_symbol,
    get_tokens_recent,
    get_tokens_summary,
    logger,
    router,
    tokens_router,
)

__all__ = ['get_context_tracker_metrics', 'get_per_turn_cost_metrics', 'get_tokens_by_cycle', 'get_tokens_by_role', 'get_tokens_by_subsystem', 'get_tokens_by_symbol', 'get_tokens_recent', 'get_tokens_summary', 'logger', 'router', 'tokens_router']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
