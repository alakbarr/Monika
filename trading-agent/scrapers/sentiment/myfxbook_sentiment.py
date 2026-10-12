"""
Compatibility facade shim for legacy myfxbook_sentiment.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.sentiment.myfxbook_sentiment.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.sentiment.myfxbook_sentiment as _canonical

from monika.infrastructure.data_ingestion.scrapers.sentiment.myfxbook_sentiment import (
    MyFxBookSentimentFetcher,
    SYMBOL_ALIASES,
    logger,
)

__all__ = ['MyFxBookSentimentFetcher', 'SYMBOL_ALIASES', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
