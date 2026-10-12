"""
Compatibility facade shim for legacy fear_greed.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.fear_greed.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.fear_greed as _canonical

from monika.infrastructure.data_ingestion.sources.fear_greed import (
    FEAR_GREED_URL,
    FearGreedFetcher,
    logger,
)

__all__ = ['FEAR_GREED_URL', 'FearGreedFetcher', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
