# ==============================================================================
# File: execution/service/order_creator.py
# ==============================================================================

"""
Order creation and parameter validation module.
Constructs validated Order entities before submission to broker adapter.
"""

import uuid
import logging
from typing import Optional, Tuple
import utils.clock as clock
from database.models import Order, OrderStatus

logger = logging.getLogger("TradingAgent.ExecutionService.OrderCreator")


class OrderCreator:
    """Helper for constructing and validating Order instances."""

    @staticmethod
    def create_order(
        symbol: str,
        order_type: str,
        direction: str,
        requested_price: float,
        requested_volume: float,
        analysis_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Instantiates an Order record with PENDING_SUBMIT status."""
        c_id = client_order_id or f"ORD_{uuid.uuid4().hex[:12]}"
        return Order(
            id=str(uuid.uuid4()),
            client_order_id=c_id,
            analysis_id=analysis_id,
            symbol=symbol,
            order_type=order_type.upper(),
            direction=direction.upper(),
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
        - direction is BUY or SELL
        - entry price is positive
        - SL is correctly positioned relative to entry (SL < entry for BUY, SL > entry for SELL)
        """
        dir_clean = direction.strip().upper()
        if dir_clean not in ("BUY", "SELL"):
            return False, f"Invalid direction '{direction}': must be BUY or SELL"

        if entry_price <= 0:
            return False, f"Invalid entry price {entry_price}: must be > 0"

        if sl is not None and sl > 0:
            if dir_clean == "BUY" and sl >= entry_price:
                return False, f"Invalid BUY SL {sl}: must be below entry {entry_price}"
            if dir_clean == "SELL" and sl <= entry_price:
                return False, f"Invalid SELL SL {sl}: must be above entry {entry_price}"

        if tp is not None and tp > 0:
            if dir_clean == "BUY" and tp <= entry_price:
                return False, f"Invalid BUY TP {tp}: must be above entry {entry_price}"
            if dir_clean == "SELL" and tp >= entry_price:
                return False, f"Invalid SELL TP {tp}: must be below entry {entry_price}"

        return True, None
