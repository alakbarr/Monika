"""
Compatibility facade shim for legacy bond_yields_fetcher.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.bond_yields_fetcher.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.bond_yields_fetcher as _canonical

from monika.infrastructure.data_ingestion.sources.bond_yields_fetcher import (
    BondYieldFetcher,
    ECB_AAA_2Y_URL,
    ECB_AAA_YIELD_URL,
    FRED_BASE_URL,
    FRED_BOND_SERIES,
    logger,
)

__all__ = ['BondYieldFetcher', 'ECB_AAA_2Y_URL', 'ECB_AAA_YIELD_URL', 'FRED_BASE_URL', 'FRED_BOND_SERIES', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
