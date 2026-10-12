"""
Compatibility facade shim for legacy delivery_ledger.py.
Re-exports from canonical monika.interfaces.gateway.delivery_ledger.
"""

from __future__ import annotations

import monika.interfaces.gateway.delivery_ledger as _canonical

from monika.interfaces.gateway.delivery_ledger import (
    DEFAULT_LEDGER_DB,
    DeliveryLedger,
    DeliveryRecord,
    DeliveryStatus,
    logger,
)

__all__ = ['DEFAULT_LEDGER_DB', 'DeliveryLedger', 'DeliveryRecord', 'DeliveryStatus', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
