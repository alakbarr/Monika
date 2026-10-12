"""
Compatibility facade shim for legacy sovereign_yield_spreads.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.sovereign_yield_spreads.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.sovereign_yield_spreads as _canonical

from monika.infrastructure.data_ingestion.sources.sovereign_yield_spreads import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    SovereignYieldSpreads,
    YieldSpreadData,
    logger,
)

__all__ = ['DEFAULT_TIMEOUT', 'DEFAULT_USER_AGENT', 'SovereignYieldSpreads', 'YieldSpreadData', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
