"""
Compatibility facade shim for legacy coinglass_funding.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.coinglass_funding.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.coinglass_funding as _canonical

from monika.infrastructure.data_ingestion.sources.coinglass_funding import (
    BINANCE_DAPI_URL,
    BINANCE_FUNDING_URL,
    BINANCE_OI_URL,
    BYBIT_TICKERS_URL,
    COINGLASS_URL,
    CoinglasFundingFetcher,
    OKX_FUNDING_URL,
    logger,
)

__all__ = ['BINANCE_DAPI_URL', 'BINANCE_FUNDING_URL', 'BINANCE_OI_URL', 'BYBIT_TICKERS_URL', 'COINGLASS_URL', 'CoinglasFundingFetcher', 'OKX_FUNDING_URL', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
