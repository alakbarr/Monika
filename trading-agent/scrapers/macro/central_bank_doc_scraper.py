"""
Compatibility facade shim for legacy central_bank_doc_scraper.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.macro.central_bank_doc_scraper.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.macro.central_bank_doc_scraper as _canonical

from monika.infrastructure.data_ingestion.scrapers.macro.central_bank_doc_scraper import (
    CentralBankDocScraper,
    DOVISH_TERMS,
    ECB_PRESS_URL,
    FED_CALENDAR_URL,
    HAWKISH_TERMS,
    logger,
)

__all__ = ['CentralBankDocScraper', 'DOVISH_TERMS', 'ECB_PRESS_URL', 'FED_CALENDAR_URL', 'HAWKISH_TERMS', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
