"""
Compatibility facade shim for legacy kitco_news.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.news.kitco_news.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.news.kitco_news as _canonical

from monika.infrastructure.data_ingestion.scrapers.news.kitco_news import (
    KitcoNewsScraper,
    logger,
)

__all__ = ['KitcoNewsScraper', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
