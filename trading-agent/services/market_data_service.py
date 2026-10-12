"""
Compatibility facade shim for legacy market_data_service.py.
Re-exports from canonical monika.application.services.market_data_service.
"""

from __future__ import annotations

import sys as _sys
import monika.application.services.market_data_service as _canonical

from monika.application.services.market_data_service import (
    MarketDataService,
    _tf_to_yfinance_interval,
    _to_yfinance_symbol,
    logger,
)

__all__ = ['MarketDataService', '_tf_to_yfinance_interval', '_to_yfinance_symbol', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
