"""
Compatibility facade shim for legacy constants.py.
Re-exports from canonical monika.core.primitives.constants.
"""

from __future__ import annotations

import monika.core.primitives.constants as _canonical

from monika.core.primitives.constants import (
    AI_MAGIC_NUMBER,
    ANALYSIS_TIMEFRAMES,
    CLAUDE_MAGIC_NUMBER,
    D1_DATA_MAX_AGE_HOURS,
    H4_DATA_MAX_AGE_HOURS,
    MARKET_OUTCOME_EXIT_REASONS,
    NON_MARKET_EXIT_REASONS,
)

__all__ = ['AI_MAGIC_NUMBER', 'ANALYSIS_TIMEFRAMES', 'CLAUDE_MAGIC_NUMBER', 'D1_DATA_MAX_AGE_HOURS', 'H4_DATA_MAX_AGE_HOURS', 'MARKET_OUTCOME_EXIT_REASONS', 'NON_MARKET_EXIT_REASONS']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
