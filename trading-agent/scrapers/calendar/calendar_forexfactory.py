"""
Compatibility facade shim for legacy calendar_forexfactory.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.calendar.calendar_forexfactory.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.calendar.calendar_forexfactory as _canonical

from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_forexfactory import (
    ForexFactoryCalendarScraper,
    fetch_forexfactory_feed_direct,
    logger,
)

__all__ = ['ForexFactoryCalendarScraper', 'fetch_forexfactory_feed_direct', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
