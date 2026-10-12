# ==============================================================================
# File: execution/service/state_machine.py
# Description: Backward-compatibility shim for monika.domain.execution.state_machine
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.state_machine
"""

import sys
import monika.domain.execution.state_machine as _canonical

from monika.domain.execution.state_machine import (
    Order,
    OrderEvent,
    OrderStateMachine,
    OrderStatus,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "Order",
    "OrderEvent",
    "OrderStateMachine",
    "OrderStatus",
    "logger",
]
