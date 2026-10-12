"""
Compatibility facade shim for legacy currency_utils.py.
Re-exports from canonical monika.domain.market.currency_utils.
"""

from __future__ import annotations

import monika.domain.market.currency_utils as _canonical

from monika.domain.market.currency_utils import (
    SYMBOL_CURRENCIES,
    get_symbol_currencies,
)

__all__ = ['SYMBOL_CURRENCIES', 'get_symbol_currencies']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
