"""
Compatibility facade shim for legacy pairing.py.
Re-exports from canonical monika.interfaces.gateway.pairing.
"""

from __future__ import annotations

import monika.interfaces.gateway.pairing as _canonical

from monika.interfaces.gateway.pairing import (
    ActivePairingRequest,
    DEFAULT_PAIRED_USERS_STORE,
    PairedUserRecord,
    PairingManager,
    get_pairing_manager,
    logger,
    reset_pairing_manager,
)

__all__ = ['ActivePairingRequest', 'DEFAULT_PAIRED_USERS_STORE', 'PairedUserRecord', 'PairingManager', 'get_pairing_manager', 'logger', 'reset_pairing_manager']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
