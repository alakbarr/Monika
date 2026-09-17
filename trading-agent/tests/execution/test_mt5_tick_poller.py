import asyncio
import time
from unittest.mock import MagicMock, patch
import pytest

from execution.mt5_client import MT5Client
from utils.protocol.event_bus import EventBus, TickPriceEvent


@pytest.fixture
def mock_settings():
    return {
        "trading": {
            "schedule": {"tick_poller_interval_seconds": 0.05},
            "asset_universe": ["EURUSD", "GBPUSD"],
        }
    }


def test_tick_poller_lifecycle_and_deduplication(mock_settings):
    client = MT5Client(mock_settings)
    client._connected = True

    event_bus = EventBus()
    received_events: list[TickPriceEvent] = []

    def on_tick(evt: TickPriceEvent):
        received_events.append(evt)

    event_bus.subscribe(TickPriceEvent, on_tick)

    # Simulated ticks
    mock_tick1 = MagicMock()
    mock_tick1.bid = 1.0850
    mock_tick1.ask = 1.0852
    mock_tick1.last = 1.0851

    mock_tick2 = MagicMock()
    mock_tick2.bid = 1.0850  # unchanged
    mock_tick2.ask = 1.0852  # unchanged
    mock_tick2.last = 1.0851

    mock_tick3 = MagicMock()
    mock_tick3.bid = 1.0855  # changed!
    mock_tick3.ask = 1.0857
    mock_tick3.last = 1.0856

    call_count = 0

    def fake_get_last_tick(sym: str):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return mock_tick1
        elif call_count <= 2:
            return mock_tick2
        else:
            return mock_tick3

    with patch("execution.mt5_client._get_last_tick", side_effect=fake_get_last_tick):
        # Start poller with 50ms interval
        client.start_tick_poller(
            symbols=["EURUSD"],
            interval_seconds=0.05,
            event_bus=event_bus,
        )

        assert client._tick_poller_thread is not None
        assert client._tick_poller_thread.is_alive()

        # Allow worker thread to run until both events received or timeout
        start_t = time.time()
        while len(received_events) < 2 and (time.time() - start_t) < 2.0:
            time.sleep(0.02)

        client.stop_tick_poller()
        assert client._tick_poller_thread is None

    # Verify deduplication
    # mock_tick1 should publish once.
    # mock_tick2 has exact same bid & ask -> deduplicated (not published).
    # mock_tick3 has new bid & ask -> published once.
    assert len(received_events) == 2
    assert received_events[0].symbol == "EURUSD"
    assert received_events[0].bid == 1.0850
    assert received_events[0].ask == 1.0852
    assert received_events[1].bid == 1.0855
    assert received_events[1].ask == 1.0857


@pytest.mark.asyncio
async def test_tick_poller_threadsafe_async(mock_settings):
    client = MT5Client(mock_settings)
    client._connected = True

    event_bus = EventBus()
    received_events: list[TickPriceEvent] = []

    async def on_tick_async(evt: TickPriceEvent):
        received_events.append(evt)

    event_bus.subscribe(TickPriceEvent, on_tick_async)

    mock_tick = MagicMock()
    mock_tick.bid = 2000.5
    mock_tick.ask = 2000.8
    mock_tick.last = 2000.6

    loop = asyncio.get_running_loop()

    with patch("execution.mt5_client._get_last_tick", return_value=mock_tick):
        client.start_tick_poller(
            symbols=["XAUUSD"],
            interval_seconds=0.05,
            event_bus=event_bus,
            loop=loop,
        )

        await asyncio.sleep(0.2)
        client.stop_tick_poller()

    assert len(received_events) == 1
    assert received_events[0].symbol == "XAUUSD"
    assert received_events[0].bid == 2000.5
    assert received_events[0].ask == 2000.8

