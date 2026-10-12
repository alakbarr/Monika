"""
Compatibility facade shim for legacy generic_gov_stats_fetcher.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.macro.generic_gov_stats_fetcher.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.macro.generic_gov_stats_fetcher as _canonical

from monika.infrastructure.data_ingestion.scrapers.macro.generic_gov_stats_fetcher import (
    FRED_API_BASE_URL,
    GenericGovStatsFetcher,
    REPORT_COMPONENT_MAP,
    logger,
)

__all__ = ['FRED_API_BASE_URL', 'GenericGovStatsFetcher', 'REPORT_COMPONENT_MAP', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
