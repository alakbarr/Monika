"""
Compatibility facade shim for legacy turn_lease.py.
Re-exports from canonical monika.interfaces.gateway.turn_lease.
"""

from __future__ import annotations

import monika.interfaces.gateway.turn_lease as _canonical

from monika.interfaces.gateway.turn_lease import (
    DEFAULT_LEASE_TTL,
    LeaseRecord,
    TurnLeaseManager,
    logger,
)

__all__ = ['DEFAULT_LEASE_TTL', 'LeaseRecord', 'TurnLeaseManager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
