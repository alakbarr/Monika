"""
Compatibility facade shim for legacy gold_physical_radar.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.gold_physical_radar.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.gold_physical_radar as _canonical

from monika.infrastructure.data_ingestion.sources.gold_physical_radar import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    GoldPhysicalRadar,
    GoldRadarSnapshot,
    logger,
)

__all__ = ['DEFAULT_TIMEOUT', 'DEFAULT_USER_AGENT', 'GoldPhysicalRadar', 'GoldRadarSnapshot', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
