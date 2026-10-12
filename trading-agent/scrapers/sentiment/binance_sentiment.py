"""
Compatibility facade shim for legacy binance_sentiment.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.sentiment.binance_sentiment.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.sentiment.binance_sentiment as _canonical

from monika.infrastructure.data_ingestion.scrapers.sentiment.binance_sentiment import (
    BINANCE_DAPI_SENTIMENT_URL,
    BINANCE_FAPI_SENTIMENT_URL,
    BinanceSentimentFetcher,
    logger,
)

__all__ = ['BINANCE_DAPI_SENTIMENT_URL', 'BINANCE_FAPI_SENTIMENT_URL', 'BinanceSentimentFetcher', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
