"""
Compatibility facade shim for legacy bias_utils.py.
Re-exports from canonical monika.domain.market.bias_utils.
"""

from __future__ import annotations

import monika.domain.market.bias_utils as _canonical

from monika.domain.market.bias_utils import (
    bias_strength,
    is_bearish,
    is_bullish,
    is_neutral,
    normalize_bias,
    normalize_currency_bias_dict,
)

__all__ = ['bias_strength', 'is_bearish', 'is_bullish', 'is_neutral', 'normalize_bias', 'normalize_currency_bias_dict']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
