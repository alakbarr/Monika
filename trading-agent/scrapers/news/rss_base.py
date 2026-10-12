"""
Compatibility facade shim for legacy rss_base.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.news.rss_base.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.news.rss_base as _canonical

from monika.infrastructure.data_ingestion.scrapers.news.rss_base import (
    RssBaseScraper,
    _TimeoutHandler,
    logger,
)

__all__ = ['RssBaseScraper', '_TimeoutHandler', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
