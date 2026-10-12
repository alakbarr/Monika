"""
Compatibility facade shim for legacy fred_treasury_yield.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.fred_treasury_yield.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.fred_treasury_yield as _canonical

from monika.infrastructure.data_ingestion.sources.fred_treasury_yield import (
    FREDDataFetcher,
    FRED_BASE_URL,
    INTEREST_RATE_SERIES,
    SERIES_TO_BANK,
    SERIES_TO_TENOR,
    TENOR_SERIES,
    _test,
    logger,
)

__all__ = ['FREDDataFetcher', 'FRED_BASE_URL', 'INTEREST_RATE_SERIES', 'SERIES_TO_BANK', 'SERIES_TO_TENOR', 'TENOR_SERIES', '_test', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
