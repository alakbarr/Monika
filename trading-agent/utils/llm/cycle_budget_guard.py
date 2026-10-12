"""
Compatibility facade shim for legacy cycle_budget_guard.py.
Re-exports from canonical monika.infrastructure.llm.cycle_budget_guard.
"""

from __future__ import annotations

import monika.infrastructure.llm.cycle_budget_guard as _canonical

from monika.infrastructure.llm.cycle_budget_guard import (
    CycleBudgetGuard,
    get_cycle_budget_guard,
)

__all__ = ['CycleBudgetGuard', 'get_cycle_budget_guard']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
