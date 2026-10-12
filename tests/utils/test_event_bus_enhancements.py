# ==============================================================================
# File: tests/utils/test_event_bus_enhancements.py
# ==============================================================================

import pytest
from datetime import datetime, timezone
from utils.protocol.event_bus import (
    EventBus,
    PreRiskGateEvent,
    PreOrderEvent,
    PostFillEvent,
    ServicePredicate,
)


@pytest.mark.asyncio
async def test_event_bus_waterfall_dispatch():
    bus = EventBus()

    # Handler 1 adds 10
    async def h1(evt: PreOrderEvent, payload: int):
        return payload + 10

    # Handler 2 multiplies by 2
    async def h2(evt: PreOrderEvent, payload: int):
        return payload * 2

    # Higher priority runs first
    bus.subscribe(PreOrderEvent, h1, priority=10)
    bus.subscribe(PreOrderEvent, h2, priority=5)

    evt = PreOrderEvent(symbol="EURUSD")
    final_payload = await bus.publish_waterfall(evt, initial_payload=5)
    # (5 + 10) * 2 = 30
    assert final_payload == 30


@pytest.mark.asyncio
async def test_event_bus_bail_dispatch():
    bus = EventBus()

    # Handler 1: doesn't block (returns None)
    async def h_pass(evt: PreRiskGateEvent):
        return None

    # Handler 2: blocks trade (returns rejection reason)
    async def h_block(evt: PreRiskGateEvent):
        return "SPREAD_TOO_HIGH"

    # Handler 3: should never run because h_block bailed
    h3_ran = False
    async def h_never(evt: PreRiskGateEvent):
        nonlocal h3_ran
        h3_ran = True
        return "ANOTHER_REASON"

    bus.subscribe(PreRiskGateEvent, h_pass, priority=20)
    bus.subscribe(PreRiskGateEvent, h_block, priority=10)
    bus.subscribe(PreRiskGateEvent, h_never, priority=5)

    evt = PreRiskGateEvent(symbol="EURUSD", direction="buy")
    result = await bus.publish_bail(evt)

    assert result == "SPREAD_TOO_HIGH"
    assert h3_ran is False


@pytest.mark.asyncio
async def test_domain_events_instantiation():
    now = datetime.now(timezone.utc)
    evt_risk = PreRiskGateEvent(symbol="GBPUSD", direction="sell", proposal={"risk": 1.0})
    assert evt_risk.symbol == "GBPUSD"
    assert evt_risk.direction == "sell"

    evt_order = PreOrderEvent(symbol="EURUSD", order_request={"lots": 0.1})
    assert evt_order.symbol == "EURUSD"

    evt_fill = PostFillEvent(ticket=123456, symbol="EURUSD", volume=0.1, price=1.0850, fill_time=now)
    assert evt_fill.ticket == 123456
    assert evt_fill.price == 1.0850


def test_service_predicates():
    ServicePredicate.reset()

    # Default unconstrained service returns True
    assert ServicePredicate.check("unknown_db") is True

    # Register passing check
    ServicePredicate.register("mt5_terminal", lambda: True)
    assert ServicePredicate.check("mt5_terminal") is True

    # Register failing check
    ServicePredicate.register("news_feed", lambda: False)
    assert ServicePredicate.check("news_feed") is False

    statuses = ServicePredicate.check_all()
    assert statuses["mt5_terminal"] is True
    assert statuses["news_feed"] is False
