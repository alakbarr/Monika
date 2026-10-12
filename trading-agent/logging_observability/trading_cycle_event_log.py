"""
Compatibility facade shim for legacy trading_cycle_event_log.py.
Re-exports from canonical monika.core.telemetry.trading_cycle_event_log.
"""

from __future__ import annotations

import monika.core.telemetry.trading_cycle_event_log as _canonical

from monika.core.telemetry.trading_cycle_event_log import (
    CycleEvent,
    CycleEventType,
    TradingCycleEventLog,
    compute_event_hash,
    get_cycle_event_log,
    logger,
    verify_chain_integrity,
)

__all__ = ['CycleEvent', 'CycleEventType', 'TradingCycleEventLog', 'compute_event_hash', 'get_cycle_event_log', 'logger', 'verify_chain_integrity']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
