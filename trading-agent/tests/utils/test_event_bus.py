import pytest
import asyncio
from utils.protocol.event_bus import (
    EventBus,
    AppEvent,
    TickPriceEvent,
    OrderStateChangedEvent,
    get_event_bus,
)


@pytest.mark.asyncio
async def test_event_bus_pub_sub_priority():
    bus = EventBus()
    call_order = []

    def normal_handler(evt):
        call_order.append("normal")

    def high_handler(evt):
        call_order.append("high")

    bus.subscribe(TickPriceEvent, normal_handler, priority=0)
    bus.subscribe(TickPriceEvent, high_handler, priority=10)

    tick = TickPriceEvent(symbol="EURUSD", bid=1.0850, ask=1.0852)
    await bus.publish(tick)

    assert call_order == ["high", "normal"]


@pytest.mark.asyncio
async def test_event_bus_backpressure_drop_oldest():
    bus = EventBus()
    # Create small queue of maxsize=2
    q = bus.get_or_create_queue("test_drop", maxsize=2)

    e1 = TickPriceEvent(symbol="EURUSD", bid=1.0)
    e2 = TickPriceEvent(symbol="EURUSD", bid=2.0)
    e3 = TickPriceEvent(symbol="EURUSD", bid=3.0)

    await bus.publish_buffered(e1, "test_drop", backpressure_mode="drop_oldest")
    await bus.publish_buffered(e2, "test_drop", backpressure_mode="drop_oldest")
    # Queue is now full [e1, e2]. Pushing e3 should drop e1
    await bus.publish_buffered(e3, "test_drop", backpressure_mode="drop_oldest")

    stats = bus.get_queue_stats("test_drop")
    assert stats["dropped_count"] == 1
    assert stats["queued_count"] == 3
    assert q.qsize() == 2

    # Verify contents are e2, e3
    item1 = q.get_nowait()
    assert item1.bid == 2.0
    item2 = q.get_nowait()
    assert item2.bid == 3.0


@pytest.mark.asyncio
async def test_event_bus_backpressure_raise():
    bus = EventBus()
    bus.get_or_create_queue("test_raise", maxsize=1)

    e1 = TickPriceEvent(symbol="EURUSD", bid=1.0)
    e2 = TickPriceEvent(symbol="EURUSD", bid=2.0)

    await bus.publish_buffered(e1, "test_raise", backpressure_mode="raise")
    with pytest.raises(asyncio.QueueFull):
        await bus.publish_buffered(e2, "test_raise", backpressure_mode="raise")


@pytest.mark.asyncio
async def test_event_bus_backpressure_block_timeout():
    bus = EventBus()
    bus.get_or_create_queue("test_block", maxsize=1)

    e1 = TickPriceEvent(symbol="EURUSD", bid=1.0)
    e2 = TickPriceEvent(symbol="EURUSD", bid=2.0)

    await bus.publish_buffered(e1, "test_block", backpressure_mode="block")
    # Attempt to block with short timeout
    success = await bus.publish_buffered(e2, "test_block", backpressure_mode="block", timeout=0.05)
    assert success is False
    stats = bus.get_queue_stats("test_block")
    assert stats["dropped_count"] == 1
