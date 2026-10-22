# ==============================================================================
# File: application/execution/service/order_lifecycle_service.py
# ==============================================================================

"""
Order Lifecycle Application Service.

Orchestrates order state transitions, database persistence of OrderEvent audit trails,
TradingEventStore audit ledger emissions, and EventBus domain event broadcasting.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives.event_bus import OrderStateChangedEvent, get_event_bus
from monika.domain.entities.order_status import OrderStatus
from monika.infrastructure.database.event_store import TradingEventStore
from monika.infrastructure.database.models import Order, OrderEvent

logger = logging.getLogger("Monika.Application.Execution.OrderLifecycleService")


class OrderLifecycleService:
    """Orchestrates order state transitions, persistence, and event broadcasting."""

    @staticmethod
    async def transition_order_state(
        session: AsyncSession,
        order: Order,
        new_status: Union[OrderStatus, str],
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        executed_price: Optional[float] = None,
        ticket: Optional[int] = None,
        slippage_pips: Optional[float] = None,
        filled_volume: Optional[float] = None,
    ) -> OrderEvent:
        """
        Record order state transition in DB (Order + OrderEvent audit trail)
        and broadcast OrderStateChangedEvent on EventBus.
        Enforces state machine rules via Order.transition_to.
        """
        evt = order.transition_to(
            new_status=new_status,
            reason=reason,
            executed_price=executed_price,
            ticket=ticket,
            slippage_pips=slippage_pips,
            filled_volume=filled_volume,
            allow_same_state=True,
        )
        old_status_val = evt.from_status
        new_status_val = evt.to_status

        session.add(evt)
        try:
            await session.flush()
        except Exception as e:
            logger.debug(f"[OrderLifecycle] flush order event error: {e}")

        # Emit to TradingEventStore
        try:
            await TradingEventStore.emit(
                session=session,
                event_type="order.state_changed",
                payload={
                    "order_id": order.id,
                    "symbol": order.symbol,
                    "old_state": old_status_val,
                    "new_state": new_status_val,
                    "reason": reason,
                    "ticket": ticket,
                    "executed_price": executed_price,
                },
                correlation_id=order.id,
                actor="order_lifecycle_service",
            )
        except Exception as es_err:
            logger.debug(f"[OrderLifecycle] TradingEventStore emit error: {es_err}")

        # Publish to EventBus
        try:
            bus = get_event_bus()
            bus_details = details or {}
            if ticket:
                bus_details["ticket"] = ticket
            if executed_price:
                bus_details["price"] = executed_price
            if reason:
                bus_details["reason"] = reason
            await bus.publish(
                OrderStateChangedEvent(
                    order_id=order.id,
                    symbol=order.symbol,
                    old_state=old_status_val,
                    new_state=new_status_val,
                    details=bus_details,
                )
            )
        except Exception as eb_err:
            logger.debug(f"[OrderLifecycle] EventBus publish error: {eb_err}")

        return evt
