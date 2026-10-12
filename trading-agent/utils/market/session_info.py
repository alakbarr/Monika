"""
Compatibility facade shim for legacy session_info.py.
Re-exports from canonical monika.domain.market.session_info.
"""

from __future__ import annotations

import monika.domain.market.session_info as _canonical

from monika.domain.market.session_info import (
    get_current_market_session,
)

__all__ = ['get_current_market_session']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
