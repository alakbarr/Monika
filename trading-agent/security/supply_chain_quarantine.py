"""
Compatibility facade shim for legacy supply_chain_quarantine.py.
Re-exports from canonical monika.core.security.supply_chain_quarantine.
"""

from __future__ import annotations

import monika.core.security.supply_chain_quarantine as _canonical

from monika.core.security.supply_chain_quarantine import (
    CRITICAL_CORE_LIBRARIES,
    DEFAULT_QUARANTINE_DAYS,
    QuarantineVerdict,
    SupplyChainQuarantine,
    logger,
)

__all__ = ['CRITICAL_CORE_LIBRARIES', 'DEFAULT_QUARANTINE_DAYS', 'QuarantineVerdict', 'SupplyChainQuarantine', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
