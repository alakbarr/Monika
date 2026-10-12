"""
Compatibility facade shim for legacy rss_marketwatch.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.news.rss_marketwatch.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.news.rss_marketwatch as _canonical

from monika.infrastructure.data_ingestion.scrapers.news.rss_marketwatch import (
    MarketwatchRssScraper,
)

__all__ = ['MarketwatchRssScraper']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
