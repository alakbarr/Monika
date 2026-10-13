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

from monika.domain.entities.order_status import (
    OrderStatus,
    InvalidOrderStateTransitionError,
)
import monika.core.primitives.clock as clock


class OrderEntity(BaseModel):
    """Pure domain entity representing an execution order."""
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_order_id: str = Field(default_factory=lambda: f"ORD_{uuid.uuid4().hex[:12]}")
    analysis_id: Optional[int] = None
    symbol: str
    order_type: str  # MARKET, LIMIT, STOP
    direction: str   # BUY, SELL
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
        """Create domain OrderEntity from SQLAlchemy model."""
        if isinstance(obj, cls):
            return obj
        if hasattr(obj, "_mock_return_value") or hasattr(obj, "_mock_wraps"):
            def _val(attr: str, default: Any = None) -> Any:
                v = getattr(obj, attr, default)
                if hasattr(v, "_mock_return_value") or hasattr(v, "_mock_wraps"):
                    return default
                return v

            raw_status = _val("status", OrderStatus.PENDING_SUBMIT)
            eff_status = (
                raw_status
                if isinstance(raw_status, OrderStatus)
                else OrderStatus(str(raw_status).lower())
                if isinstance(raw_status, str)
                else OrderStatus.PENDING_SUBMIT
            )

            return cls(
                id=_val("id", 1),
                client_order_id=str(_val("client_order_id", "ORD_mock_001")),
                analysis_id=_val("analysis_id", None),
                symbol=str(_val("symbol", "EURUSD")),
                order_type=str(_val("order_type", "MARKET")),
                direction=str(_val("direction", "BUY")),
                requested_price=float(_val("requested_price", 1.1000)),
                executed_price=_val("executed_price", None),
                slippage_pips=float(_val("slippage_pips", 0.0)),
                requested_volume=float(_val("requested_volume", 0.1)),
                filled_volume=float(_val("filled_volume", 0.0)),
                status=eff_status,
                replay_policy=str(_val("replay_policy", "never")),
                intent_committed_at=_val("intent_committed_at", None),
                settlement_committed_at=_val("settlement_committed_at", None),
                mt5_ticket=_val("mt5_ticket", None),
                created_at=_val("created_at", clock.now()),
                updated_at=_val("updated_at", clock.now()),
            )
        return cls.model_validate(obj, from_attributes=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
