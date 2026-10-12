"""
Compatibility facade shim for legacy models.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.models.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.models as _canonical

from monika.infrastructure.data_ingestion.scrapers.models import (
    CalendarEvent,
    FedMeeting,
    FedProbability,
    ScrapedNews,
    ScrapedTweet,
)

__all__ = ['CalendarEvent', 'FedMeeting', 'FedProbability', 'ScrapedNews', 'ScrapedTweet']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
