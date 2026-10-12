"""
Compatibility facade shim for legacy validators.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.validators.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.validators as _canonical

from monika.infrastructure.data_ingestion.sources.validators import (
    INTRADAY_CACHE_TTL_SECONDS,
    MAX_OHLCV_STALE_DAYS,
    NoMarketDataError,
    NonMonotonicDataError,
    StaleDataError,
    _parse_timestamp,
    is_intraday_cache_expired,
    logger,
    validate_ohlcv_freshness,
)

__all__ = ['INTRADAY_CACHE_TTL_SECONDS', 'MAX_OHLCV_STALE_DAYS', 'NoMarketDataError', 'NonMonotonicDataError', 'StaleDataError', '_parse_timestamp', 'is_intraday_cache_expired', 'logger', 'validate_ohlcv_freshness']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
