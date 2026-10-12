"""
Compatibility facade shim for legacy rss_dow_jones.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.news.rss_dow_jones.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.news.rss_dow_jones as _canonical

from monika.infrastructure.data_ingestion.scrapers.news.rss_dow_jones import (
    DowJonesRssScraper,
)

__all__ = ['DowJonesRssScraper']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
