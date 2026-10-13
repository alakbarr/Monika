"""
Compatibility facade shim for legacy event_bus.py.
Re-exports from canonical monika.core.primitives.event_bus.
"""

from __future__ import annotations

import monika.core.primitives.event_bus as _canonical

from monika.core.primitives.event_bus import (
    AppEvent,
    BarClosedEvent,
    CircuitBreakerEvent,
    E,
    EventBus,
    OrderStateChangedEvent,
    PostFillEvent,
    PreOrderEvent,
    PreRiskGateEvent,
    RiskBreachEvent,
    ServicePredicate,
    Subscription,
    TickPriceEvent,
    get_event_bus,
    logger,
    reset_event_bus,
)

__all__ = [
    "AppEvent",
    "BarClosedEvent",
    "CircuitBreakerEvent",
    "E",
    "EventBus",
    "OrderStateChangedEvent",
    "PostFillEvent",
    "PreOrderEvent",
    "PreRiskGateEvent",
    "RiskBreachEvent",
    "ServicePredicate",
    "Subscription",
    "TickPriceEvent",
    "get_event_bus",
    "logger",
    "reset_event_bus",
]


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith("__") and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys

_sys.modules[__name__] = _canonical
