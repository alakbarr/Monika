"""
Compatibility facade shim for legacy usd_strength_proxy.py.
Re-exports from canonical monika.domain.market.usd_strength_proxy.
"""

from __future__ import annotations

import monika.domain.market.usd_strength_proxy as _canonical

from monika.domain.market.usd_strength_proxy import (
    compute_usd_strength_proxy,
)

__all__ = ['compute_usd_strength_proxy']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
