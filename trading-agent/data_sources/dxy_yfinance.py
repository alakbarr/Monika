"""
Compatibility facade shim for legacy dxy_yfinance.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.dxy_yfinance.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.dxy_yfinance as _canonical

from monika.infrastructure.data_ingestion.sources.dxy_yfinance import (
    DXYFetcher,
    DXY_TICKER,
    YAHOO_CHART_URLS,
    logger,
)

__all__ = ['DXYFetcher', 'DXY_TICKER', 'YAHOO_CHART_URLS', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
