# ==============================================================================
# File: execution/order_emulator.py
# Description: Backward-compatibility shim for monika.domain.execution.order_emulator
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.order_emulator
"""

import sys
import monika.domain.execution.order_emulator as _canonical

from monika.domain.execution.order_emulator import (
    ClientOrderEmulator,
    EventBus,
    PendingOrder,
    TickPriceEvent,
    TrackedPosition,
    evaluate_pending_order,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ClientOrderEmulator",
    "EventBus",
    "PendingOrder",
    "TickPriceEvent",
    "TrackedPosition",
    "evaluate_pending_order",
    "logger",
]
