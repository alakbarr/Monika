"""
Compatibility facade shim for legacy brent_yfinance.py.
Re-exports from canonical monika.domain.market.brent_yfinance.
"""

from __future__ import annotations

import monika.domain.market.brent_yfinance as _canonical

from monika.domain.market.brent_yfinance import (
    get_brent_price,
)

__all__ = ['get_brent_price']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
