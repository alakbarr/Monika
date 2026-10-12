"""
Compatibility facade shim for legacy credit_balance_tracker.py.
Re-exports from canonical monika.infrastructure.api.credit_balance_tracker.
"""

from __future__ import annotations

import monika.infrastructure.api.credit_balance_tracker as _canonical

from monika.infrastructure.api.credit_balance_tracker import (
    CreditBalanceTracker,
)

__all__ = ['CreditBalanceTracker']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
