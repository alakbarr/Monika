"""
Compatibility facade shim for legacy base_scraper.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.base_scraper.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.base_scraper as _canonical

from monika.infrastructure.data_ingestion.scrapers.base_scraper import (
    BaseScraper,
    kill_process_tree,
    logger,
)

__all__ = ['BaseScraper', 'kill_process_tree', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
