"""
Compatibility facade shim for legacy central_bank_watch.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.central_bank_watch.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.central_bank_watch as _canonical

from monika.infrastructure.data_ingestion.sources.central_bank_watch import (
    CARD_CLASS_TO_BANK,
    CBW_BASE_URL,
    CBW_YIELD_URL,
    CentralBankWatchFetcher,
    DEFAULT_HEADERS,
    logger,
)

__all__ = ['CARD_CLASS_TO_BANK', 'CBW_BASE_URL', 'CBW_YIELD_URL', 'CentralBankWatchFetcher', 'DEFAULT_HEADERS', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
