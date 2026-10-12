"""
Compatibility facade shim for legacy vix_yfinance.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.vix_yfinance.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.vix_yfinance as _canonical

from monika.infrastructure.data_ingestion.sources.vix_yfinance import (
    CBOE_VIX_CSV_URL,
    FRED_BASE_URL,
    VIXFetcher,
    VIX_TICKER,
    YAHOO_VIX_CHART_URL,
    _test,
    logger,
)

__all__ = ['CBOE_VIX_CSV_URL', 'FRED_BASE_URL', 'VIXFetcher', 'VIX_TICKER', 'YAHOO_VIX_CHART_URL', '_test', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
