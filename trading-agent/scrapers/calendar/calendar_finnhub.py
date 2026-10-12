"""
Compatibility facade shim for legacy calendar_finnhub.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.calendar.calendar_finnhub.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.calendar.calendar_finnhub as _canonical

from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_finnhub import (
    COUNTRY_TO_CURRENCY,
    FinnhubCalendarScraper,
    _IMPACT_MAP,
    logger,
)

__all__ = ['COUNTRY_TO_CURRENCY', 'FinnhubCalendarScraper', '_IMPACT_MAP', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
