import pytest
from unittest.mock import AsyncMock, MagicMock

from execution.health_check import FlakeTolerantHealthChecker


@pytest.mark.asyncio
async def test_cached_positive():
    mock_client = AsyncMock()
    mock_client.is_connected = AsyncMock(return_value=True)

    current_time = 100.0
    def time_provider():
        return current_time

    checker = FlakeTolerantHealthChecker(mock_client, ttl_seconds=30.0, grace_seconds=60.0, time_provider=time_provider)

    # First call: hits client
    res1 = await checker.is_healthy()
    assert res1 is True
    assert mock_client.is_connected.call_count == 1

    # Second call at t=110 (10s later, within 30s TTL): served from cache
    current_time = 110.0
    res2 = await checker.is_healthy()
    assert res2 is True
    assert mock_client.is_connected.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_force_check_bypasses_cache():
    mock_client = AsyncMock()
    mock_client.is_connected = AsyncMock(return_value=True)

    current_time = 100.0
    checker = FlakeTolerantHealthChecker(mock_client, ttl_seconds=30.0, time_provider=lambda: current_time)

    await checker.is_healthy()
    assert mock_client.is_connected.call_count == 1

    # Force check bypasses cache
    await checker.is_healthy(force_check=True)
    assert mock_client.is_connected.call_count == 2


@pytest.mark.asyncio
async def test_grace_period_suppresses_transient_failure():
    mock_client = AsyncMock()
    # First success, then exception
    mock_client.is_connected = AsyncMock(side_effect=[True, RuntimeError("Socket blip")])

    current_time = 100.0
    def time_provider():
        return current_time

    checker = FlakeTolerantHealthChecker(mock_client, ttl_seconds=30.0, grace_seconds=60.0, time_provider=time_provider)

    # Initial success at t=100
    assert await checker.is_healthy() is True

    # At t=135s (> 30s TTL, but within 60s grace period since t=100)
    current_time = 135.0
    assert await checker.is_healthy() is True  # Flake suppressed by grace period


@pytest.mark.asyncio
async def test_grace_period_expiration_triggers_failure():
    mock_client = AsyncMock()
    mock_client.is_connected = AsyncMock(side_effect=[True, False])

    current_time = 100.0
    def time_provider():
        return current_time

    checker = FlakeTolerantHealthChecker(mock_client, ttl_seconds=30.0, grace_seconds=60.0, time_provider=time_provider)

    # Initial success at t=100
    assert await checker.is_healthy() is True

    # At t=165s (> 60s grace period since last success)
    current_time = 165.0
    assert await checker.is_healthy() is False


@pytest.mark.asyncio
async def test_cold_start_failure():
    mock_client = AsyncMock()
    mock_client.is_connected = AsyncMock(return_value=False)

    checker = FlakeTolerantHealthChecker(mock_client, ttl_seconds=30.0, grace_seconds=60.0)
    assert await checker.is_healthy() is False


@pytest.mark.asyncio
async def test_record_success_and_failure():
    mock_client = AsyncMock()
    current_time = 100.0
    checker = FlakeTolerantHealthChecker(mock_client, ttl_seconds=30.0, time_provider=lambda: current_time)

    checker.record_success()
    status = checker.get_status()
    assert status["cached_valid"] is True

    checker.record_failure()
    status_after = checker.get_status()
    assert status_after["cached_valid"] is False
    assert status_after["in_grace"] is False
