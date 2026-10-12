"""
Compatibility facade shim for legacy token_budgeter.py.
Re-exports from canonical monika.core.telemetry.token_budgeter.
"""

from __future__ import annotations

import monika.core.telemetry.token_budgeter as _canonical

from monika.core.telemetry.token_budgeter import (
    DEFAULT_DAILY_BUDGET,
    SUBSYSTEM_SHARES,
    TokenBudgetManager,
    get_token_budgeter,
    logger,
)

__all__ = ['DEFAULT_DAILY_BUDGET', 'SUBSYSTEM_SHARES', 'TokenBudgetManager', 'get_token_budgeter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
