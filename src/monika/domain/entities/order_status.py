# ==============================================================================
# File: domain/entities/order_status.py
# ==============================================================================

"""
Order Status Domain Enum and State Transition Graph.

Defines the formal finite state machine values and valid transitions
for order lifecycle management, free from database or ORM dependencies.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set, Union


class InvalidOrderStateTransitionError(ValueError):
    """Raised when an illegal order lifecycle state transition is attempted."""

    pass


class OrderStatus(str, Enum):
    """Order lifecycle status domain enum."""

    PENDING_SUBMIT = "pending_submit"
    INTENT_COMMITTED = "intent_committed"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    ABORT_REQUESTED = "abort_requested"

    @property
    def is_terminal(self) -> bool:
        """Returns True if state is terminal and cannot transition further."""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.CANCELLED,
            OrderStatus.INTERRUPTED,
            OrderStatus.ABORT_REQUESTED,
        )

    def can_transition_to(self, target: Union[OrderStatus, str]) -> bool:
        """Check if target state is a valid transition from current state."""
        if isinstance(target, str):
            try:
                target = OrderStatus(target)
            except ValueError:
                return False
        if self == target:
            return True
        return target in VALID_ORDER_TRANSITIONS.get(self, set())


# Valid state machine transition graph
VALID_ORDER_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.PENDING_SUBMIT: {
        OrderStatus.PENDING_SUBMIT,
        OrderStatus.INTENT_COMMITTED,
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.ABORT_REQUESTED,
    },
    OrderStatus.INTENT_COMMITTED: {
        OrderStatus.INTENT_COMMITTED,
        OrderStatus.SUBMITTED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.ABORT_REQUESTED,
        OrderStatus.INTERRUPTED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.SUBMITTED,
        OrderStatus.ACCEPTED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.INTERRUPTED,
        OrderStatus.ABORT_REQUESTED,
    },
    OrderStatus.ACCEPTED: {
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
        OrderStatus.INTERRUPTED,
        OrderStatus.ABORT_REQUESTED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.INTERRUPTED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.INTERRUPTED: set(),
    OrderStatus.ABORT_REQUESTED: set(),
}
