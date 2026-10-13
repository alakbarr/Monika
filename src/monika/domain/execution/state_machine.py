# ==============================================================================
# File: domain/execution/state_machine.py
# ==============================================================================

"""
Order State Machine Transition Engine.

Pure domain state machine managing in-memory order status transitions
and rule validation, completely decoupled from database sessions,
event stores, and event buses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from monika.domain.entities.order_status import (
    OrderStatus,
    InvalidOrderStateTransitionError,
    VALID_ORDER_TRANSITIONS,
)

logger = logging.getLogger("Monika.Domain.Execution.OrderStateMachine")


class OrderStateMachine:
    """Pure domain state machine for order lifecycle transitions."""

    @staticmethod
    def can_transition(
        current_status: Union[OrderStatus, str],
        new_status: Union[OrderStatus, str],
    ) -> bool:
        """Check if target state is a valid transition from current state."""
        curr = current_status if isinstance(current_status, OrderStatus) else OrderStatus(current_status)
        return curr.can_transition_to(new_status)

    @staticmethod
    def transition(
        order: Any,
        new_status: Union[OrderStatus, str],
        reason: Optional[str] = None,
        executed_price: Optional[float] = None,
        ticket: Optional[int] = None,
        slippage_pips: Optional[float] = None,
        filled_volume: Optional[float] = None,
        allow_same_state: bool = True,
    ) -> Any:
        """
        Pure in-memory transition for an order entity or model.
        Enforces state machine rules and mutates the order in memory.
        Returns the transition event or event payload.
        """
        if hasattr(order, "transition_to"):
            return order.transition_to(
                new_status=new_status,
                reason=reason,
                executed_price=executed_price,
                ticket=ticket,
                slippage_pips=slippage_pips,
                filled_volume=filled_volume,
                allow_same_state=allow_same_state,
            )

        target = new_status if isinstance(new_status, OrderStatus) else OrderStatus(new_status)
        curr = order.status if isinstance(order.status, OrderStatus) else OrderStatus(order.status)

        if curr == target and not allow_same_state:
            raise InvalidOrderStateTransitionError(
                f"Cannot transition order from {curr.value} to same state {target.value}"
            )

        if curr != target and not curr.can_transition_to(target):
            raise InvalidOrderStateTransitionError(f"Illegal order state transition: {curr.value} -> {target.value}")

        order.status = target
        return {
            "order_id": getattr(order, "id", None),
            "from_status": curr.value,
            "to_status": target.value,
            "reason": reason,
            "executed_price": executed_price,
            "ticket": ticket,
            "slippage_pips": slippage_pips,
            "filled_volume": filled_volume,
        }

    @staticmethod
    async def transition_order_state(
        session: Any,
        order: Any,
        new_status: Any,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        executed_price: Optional[float] = None,
        ticket: Optional[int] = None,
        slippage_pips: Optional[float] = None,
        filled_volume: Optional[float] = None,
    ) -> Any:
        """
        Backward-compatibility facade method.
        Delegates persistence and event orchestration to OrderLifecycleService.
        """
        from monika.application.execution.service.order_lifecycle_service import OrderLifecycleService

        return await OrderLifecycleService.transition_order_state(
            session=session,
            order=order,
            new_status=new_status,
            reason=reason,
            details=details,
            executed_price=executed_price,
            ticket=ticket,
            slippage_pips=slippage_pips,
            filled_volume=filled_volume,
        )


__all__ = [
    "OrderStateMachine",
    "OrderStatus",
    "InvalidOrderStateTransitionError",
    "VALID_ORDER_TRANSITIONS",
]
