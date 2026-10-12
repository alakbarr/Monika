# ==============================================================================
# File: execution/service/state_machine.py
# ==============================================================================

"""
Order state machine transition engine and event publisher.
Manages Order -> OrderEvent audit trail and EventBus lifecycle broadcast.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Order, OrderStatus, OrderEvent

logger = logging.getLogger("TradingAgent.ExecutionService.StateMachine")


class OrderStateMachine:
    """Manages order state transitions and event emission."""

    @staticmethod
    async def transition_order_state(
        session: AsyncSession,
        order: Order,
        new_status: OrderStatus,
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
            from database.event_store import TradingEventStore
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
                actor="state_machine",
            )
        except Exception as es_err:
            logger.debug(f"[OrderLifecycle] TradingEventStore emit error: {es_err}")

        # Publish to EventBus
        try:
            from utils.protocol.event_bus import get_event_bus, OrderStateChangedEvent
            bus = get_event_bus()
            bus_details = details or {}
            if ticket:
                bus_details["ticket"] = ticket
            if executed_price:
                bus_details["price"] = executed_price
            if reason:
                bus_details["reason"] = reason
            await bus.publish(OrderStateChangedEvent(
                order_id=order.id,
                symbol=order.symbol,
                old_state=old_status_val,
                new_state=new_status_val,
                details=bus_details,
            ))
        except Exception as eb_err:
            logger.debug(f"[OrderLifecycle] EventBus publish error: {eb_err}")

        return evt
