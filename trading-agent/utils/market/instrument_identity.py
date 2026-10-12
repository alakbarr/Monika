"""
Compatibility facade shim for legacy instrument_identity.py.
Re-exports from canonical monika.domain.market.instrument_identity.
"""

from __future__ import annotations

import monika.domain.market.instrument_identity as _canonical

from monika.domain.market.instrument_identity import (
    InstrumentIdentity,
    resolve_instrument_identity,
)

__all__ = ['InstrumentIdentity', 'resolve_instrument_identity']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
