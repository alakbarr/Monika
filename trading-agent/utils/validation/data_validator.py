"""
Compatibility facade shim for legacy data_validator.py.
Re-exports from canonical monika.core.validation.data_validator.
"""

from __future__ import annotations

import monika.core.validation.data_validator as _canonical

from monika.core.validation.data_validator import (
    DEFAULT_IND_AGE,
    DEFAULT_MACRO_AGE_DAYS,
    DEFAULT_OHLCV_AGE,
    check_data_coherence,
    is_crypto_symbol,
    is_forex_market_closed,
    is_market_reopen_window,
    is_spread_acceptable,
    validate_data_freshness,
)

__all__ = ['DEFAULT_IND_AGE', 'DEFAULT_MACRO_AGE_DAYS', 'DEFAULT_OHLCV_AGE', 'check_data_coherence', 'is_crypto_symbol', 'is_forex_market_closed', 'is_market_reopen_window', 'is_spread_acceptable', 'validate_data_freshness']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
