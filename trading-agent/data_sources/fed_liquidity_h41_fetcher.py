"""
Compatibility facade shim for legacy fed_liquidity_h41_fetcher.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.fed_liquidity_h41_fetcher.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.fed_liquidity_h41_fetcher as _canonical

from monika.infrastructure.data_ingestion.sources.fed_liquidity_h41_fetcher import (
    FRED_SERIES_RRP,
    FRED_SERIES_TGA,
    FRED_SERIES_WALCL,
    FedLiquidityH41Fetcher,
    logger,
)

__all__ = ['FRED_SERIES_RRP', 'FRED_SERIES_TGA', 'FRED_SERIES_WALCL', 'FedLiquidityH41Fetcher', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
