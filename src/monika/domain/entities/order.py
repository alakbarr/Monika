# ==============================================================================
# File: domain/entities/order.py
# ==============================================================================

"""
Order Domain Entity.

Pure domain representation of an execution order, isolated from ORM mapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

import monika.core.primitives.clock as clock
from monika.domain.entities.order_status import (
    InvalidOrderStateTransitionError,
    OrderStatus,
)


class OrderEntity(BaseModel):
    """Pure domain entity representing an execution order."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_order_id: str = Field(default_factory=lambda: f"ORD_{uuid.uuid4().hex[:12]}")
    analysis_id: Optional[int] = None
    symbol: str
    order_type: str  # MARKET, LIMIT, STOP
    direction: str  # BUY, SELL
    requested_price: float
    executed_price: Optional[float] = None
    slippage_pips: float = 0.0
    requested_volume: float
    filled_volume: float = 0.0
    status: OrderStatus = OrderStatus.PENDING_SUBMIT
    replay_policy: str = "never"
    intent_committed_at: Optional[datetime] = None
    settlement_committed_at: Optional[datetime] = None
    mt5_ticket: Optional[int] = None
    created_at: datetime = Field(default_factory=clock.now)
    updated_at: datetime = Field(default_factory=clock.now)

    @property
    def is_terminal(self) -> bool:
        """Returns True if the order is in a terminal state."""
        return self.status.is_terminal

    def can_transition_to(self, target: Union[OrderStatus, str]) -> bool:
        """Check whether transition to target state is legally permissible."""
        return self.status.can_transition_to(target)

    def transition_to(
        self,
        new_status: Union[OrderStatus, str],
        reason: Optional[str] = None,
        executed_price: Optional[float] = None,
        ticket: Optional[int] = None,
        slippage_pips: Optional[float] = None,
        filled_volume: Optional[float] = None,
        allow_same_state: bool = True,
    ) -> Dict[str, Any]:
        """
        Pure in-memory transition to a new status.
        Raises InvalidOrderStateTransitionError if illegal.
        Returns a dict representing the transition event details.
        """
        target = new_status if isinstance(new_status, OrderStatus) else OrderStatus(new_status)
        curr = self.status

        if curr == target and not allow_same_state:
            raise InvalidOrderStateTransitionError(
                f"Cannot transition order {self.id} from {curr.value} to same state {target.value}"
            )

        if curr != target and not curr.can_transition_to(target):
            raise InvalidOrderStateTransitionError(
                f"Illegal order state transition for order {self.id}: {curr.value} -> {target.value}"
            )

        from_status_val = curr.value
        to_status_val = target.value

        self.status = target
        self.updated_at = clock.now()

        if executed_price is not None:
            self.executed_price = executed_price
        if ticket is not None:
            self.mt5_ticket = ticket
        if slippage_pips is not None:
            self.slippage_pips = slippage_pips
        if filled_volume is not None:
            self.filled_volume = filled_volume

        if target == OrderStatus.INTENT_COMMITTED and not self.intent_committed_at:
            self.intent_committed_at = clock.now()
        elif target == OrderStatus.FILLED and not self.settlement_committed_at:
            self.settlement_committed_at = clock.now()

        return {
            "order_id": self.id,
            "from_status": from_status_val,
            "to_status": to_status_val,
            "reason": reason,
            "executed_price": executed_price,
            "ticket": ticket,
            "slippage_pips": slippage_pips,
            "filled_volume": filled_volume,
            "timestamp": clock.now(),
        }

    @classmethod
    def from_orm(cls, obj: Any) -> OrderEntity:
        """Create domain OrderEntity from ORM model or compatible object."""
        if isinstance(obj, cls):
            return obj
        return cls.model_validate(obj, from_attributes=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
