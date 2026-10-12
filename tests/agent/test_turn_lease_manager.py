import asyncio
import pytest
from unittest.mock import MagicMock
from agent.turn_lease_manager import SymbolTurnLeaseManager, get_symbol_lease_manager


@pytest.mark.asyncio
async def test_lease_acquire_and_release():
    manager = SymbolTurnLeaseManager()
    ok = await manager.acquire_lease("EURUSD", "cycle_stage2", ttl_seconds=60.0)
    assert ok is True
    assert await manager.is_symbol_leased("EURUSD") is True
    assert await manager.get_lease_holder("EURUSD") == "cycle_stage2"

    released = await manager.release_lease("EURUSD", "cycle_stage2")
    assert released is True
    assert await manager.is_symbol_leased("EURUSD") is False
    assert await manager.get_lease_holder("EURUSD") is None


@pytest.mark.asyncio
async def test_lease_collision_denial():
    manager = SymbolTurnLeaseManager()
    ok1 = await manager.acquire_lease("XAUUSD", "cycle_scheduler", ttl_seconds=60.0)
    assert ok1 is True

    # Second acquirer should be denied
    ok2 = await manager.acquire_lease("XAUUSD", "reactive_news", ttl_seconds=60.0)
    assert ok2 is False
    assert await manager.get_lease_holder("XAUUSD") == "cycle_scheduler"


@pytest.mark.asyncio
async def test_lease_expiration():
    manager = SymbolTurnLeaseManager()
    # Acquire with tiny TTL
    await manager.acquire_lease("GBPUSD", "worker_1", ttl_seconds=0.05)
    assert await manager.is_symbol_leased("GBPUSD") is True

    await asyncio.sleep(0.08)
    assert await manager.is_symbol_leased("GBPUSD") is False

    # After expiry, worker_2 can acquire
    ok = await manager.acquire_lease("GBPUSD", "worker_2", ttl_seconds=60.0)
    assert ok is True
    assert await manager.get_lease_holder("GBPUSD") == "worker_2"


@pytest.mark.asyncio
async def test_event_coalescence_into_active_harness():
    manager = SymbolTurnLeaseManager()
    mock_harness = MagicMock()
    mock_harness.enqueue_steering = MagicMock()

    # Acquire lease with active harness registered
    ok = await manager.acquire_lease("USDJPY", "stage2_runner", ttl_seconds=120.0, active_harness=mock_harness)
    assert ok is True

    # Reactive event arrives while analysis is running
    coalesced = await manager.coalesce_event(
        symbol="USDJPY",
        event_text="BOJ unexpected rate hike comment",
        sender="breaking_news",
    )
    assert coalesced is True
    mock_harness.enqueue_steering.assert_called_once_with(
        content="BOJ unexpected rate hike comment",
        sender="breaking_news",
        mode="immediate",
    )


@pytest.mark.asyncio
async def test_event_coalescence_fails_when_no_active_lease():
    manager = SymbolTurnLeaseManager()
    # No lease for AUDUSD
    coalesced = await manager.coalesce_event(
        symbol="AUDUSD",
        event_text="RBA statement released",
        sender="calendar_poller",
    )
    assert coalesced is False
