"""
Compatibility facade shim for legacy dynamic_correlation.py.
Re-exports from canonical monika.domain.market.dynamic_correlation.
"""

from __future__ import annotations

import monika.domain.market.dynamic_correlation as _canonical

from monika.domain.market.dynamic_correlation import (
    STATIC_CORRELATION_FALLBACK,
    YIELD_TENOR_MAP,
    compute_cross_asset_macro_correlation,
    get_correlation_uncertainty_multiplier,
    get_rolling_correlation,
    is_crypto_or_commodity_symbol,
    _static_fallback,
)

__all__ = ['STATIC_CORRELATION_FALLBACK', 'YIELD_TENOR_MAP', 'compute_cross_asset_macro_correlation', 'get_correlation_uncertainty_multiplier', 'get_rolling_correlation', 'is_crypto_or_commodity_symbol', '_static_fallback']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
