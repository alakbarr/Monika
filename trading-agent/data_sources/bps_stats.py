"""
Compatibility facade shim for legacy bps_stats.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.bps_stats.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.bps_stats as _canonical

from monika.infrastructure.data_ingestion.sources.bps_stats import (
    BPSStatsFetcher,
    logger,
)

__all__ = ['BPSStatsFetcher', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
