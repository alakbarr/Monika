# ==============================================================================
# File: execution/service/order_creator.py
# Description: Backward-compatibility shim for monika.domain.execution.order_creator
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.order_creator
"""

import sys
import monika.domain.execution.order_creator as _canonical

from monika.domain.execution.order_creator import (
    Order,
    OrderCreator,
    OrderStatus,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "Order",
    "OrderCreator",
    "OrderStatus",
    "logger",
]
