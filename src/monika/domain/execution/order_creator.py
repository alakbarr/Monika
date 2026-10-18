# ==============================================================================
# File: execution/service/order_creator.py
# ==============================================================================

"""
Order creation and parameter validation module.
Constructs validated Order entities before submission to broker adapter.
"""

import logging
import math
import uuid
from typing import Any, Optional, Tuple

import monika.core.primitives.clock as clock
from monika.domain.entities.order_status import OrderStatus

logger = logging.getLogger("TradingAgent.ExecutionService.OrderCreator")


def get_order_class() -> Any:
    """Dynamically resolves order class without static infrastructure coupling."""
    return OrderCreator.get_order_class()


class OrderCreator:
    """Helper for constructing and validating Order instances."""

    _order_class: Optional[Any] = None

    @classmethod
    def get_order_class(cls) -> Any:
        """Resolves order class (defaults to pure domain OrderEntity)."""
        if cls._order_class is None:
            from monika.domain.entities.order import OrderEntity

            cls._order_class = OrderEntity
        return cls._order_class

    @classmethod
    def set_order_class(cls, order_cls: Optional[Any]) -> None:
        """Explicitly set or override order model/entity class."""
        cls._order_class = order_cls

    @classmethod
    def reset(cls) -> None:
        """Reset cached order class to None (for test isolation)."""
        cls._order_class = None

    @classmethod
    def create_order(
        cls,
        symbol: str,
        order_type: str,
        direction: str,
        requested_price: float,
        requested_volume: float,
        analysis_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> Any:
        """Instantiates an Order record with PENDING_SUBMIT status."""
        if not symbol or not symbol.strip():
            raise ValueError("Cannot create order: symbol must be a non-empty string")
        if requested_volume <= 0 or math.isnan(requested_volume) or math.isinf(requested_volume):
            raise ValueError(f"Cannot create order: requested_volume ({requested_volume}) must be strictly positive")
        if requested_price <= 0 or math.isnan(requested_price) or math.isinf(requested_price):
            raise ValueError(f"Cannot create order: requested_price ({requested_price}) must be strictly positive")
        dir_clean = (direction or "").strip().upper()
        if dir_clean not in ("BUY", "SELL"):
            raise ValueError(f"Cannot create order: direction must be BUY or SELL (got '{direction}')")

        c_id = client_order_id or f"ORD_{uuid.uuid4().hex[:12]}"
        order_cls = cls.get_order_class()
        return order_cls(
            id=str(uuid.uuid4()),
            client_order_id=c_id,
            analysis_id=analysis_id,
            symbol=symbol.strip().upper(),
            order_type=order_type.strip().upper(),
            direction=dir_clean,
            requested_price=float(requested_price),
            requested_volume=float(requested_volume),
            status=OrderStatus.PENDING_SUBMIT,
            created_at=clock.now(),
            updated_at=clock.now(),
        )

    @staticmethod
    def validate_order_parameters(
        symbol: str,
        direction: str,
        entry_price: float,
        sl: Optional[float],
        tp: Optional[float],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates core parameters of an order:
        - symbol is non-empty
        - direction is BUY or SELL
        - entry price is positive
        - SL is correctly positioned relative to entry (SL < entry for BUY, SL > entry for SELL)
        - SL and TP are strictly positive if provided
        """
        if not symbol or not symbol.strip():
            return False, "Invalid symbol: must be a non-empty string"

        dir_clean = (direction or "").strip().upper()
        if dir_clean not in ("BUY", "SELL"):
            return False, f"Invalid direction '{direction}': must be BUY or SELL"

        if entry_price <= 0 or math.isnan(entry_price):
            return False, f"Invalid entry price {entry_price}: must be > 0"

        if sl is not None:
            if sl <= 0 or math.isnan(sl):
                return False, f"Invalid Stop Loss {sl}: must be > 0"
            if dir_clean == "BUY" and sl >= entry_price:
                return False, f"Invalid BUY SL {sl}: must be below entry {entry_price}"
            if dir_clean == "SELL" and sl <= entry_price:
                return False, f"Invalid SELL SL {sl}: must be above entry {entry_price}"

        if tp is not None:
            if tp <= 0 or math.isnan(tp):
                return False, f"Invalid Take Profit {tp}: must be > 0"
            if dir_clean == "BUY" and tp <= entry_price:
                return False, f"Invalid BUY TP {tp}: must be above entry {entry_price}"
            if dir_clean == "SELL" and tp >= entry_price:
                return False, f"Invalid SELL TP {tp}: must be below entry {entry_price}"

        return True, None
