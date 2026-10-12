"""
Compatibility facade shim for legacy rss_wsj.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.news.rss_wsj.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.news.rss_wsj as _canonical

from monika.infrastructure.data_ingestion.scrapers.news.rss_wsj import (
    WsjRssScraper,
)

__all__ = ['WsjRssScraper']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
