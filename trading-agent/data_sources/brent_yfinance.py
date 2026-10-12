"""
Compatibility facade shim for legacy brent_yfinance.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.brent_yfinance.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.brent_yfinance as _canonical

from monika.infrastructure.data_ingestion.sources.brent_yfinance import (
    get_brent_price,
)

__all__ = ['get_brent_price']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
