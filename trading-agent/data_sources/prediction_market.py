"""
Compatibility facade shim for legacy prediction_market.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.prediction_market.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.prediction_market as _canonical

from monika.infrastructure.data_ingestion.sources.prediction_market import (
    CLOB_BOOK_URL,
    DEFAULT_MACRO_QUERIES,
    GAMMA_API_URL,
    PredictionMarketClient,
    logger,
)

__all__ = ['CLOB_BOOK_URL', 'DEFAULT_MACRO_QUERIES', 'GAMMA_API_URL', 'PredictionMarketClient', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
