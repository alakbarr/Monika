"""
Compatibility facade shim for legacy market_stress_auction_fetcher.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.market_stress_auction_fetcher.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.market_stress_auction_fetcher as _canonical

from monika.infrastructure.data_ingestion.sources.market_stress_auction_fetcher import (
    MarketStressAuctionFetcher,
    TENOR_TERM_MAP,
    TREASURY_DIRECT_API,
    logger,
)

__all__ = ['MarketStressAuctionFetcher', 'TENOR_TERM_MAP', 'TREASURY_DIRECT_API', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
