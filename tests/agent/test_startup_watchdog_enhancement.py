"""
Tests for PR-22: Startup Watchdog Enhancement.
Verifies broker ping, data feed freshness check, position reconciliation, and cold-start pre-flight.
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.monitors.startup_watchdog import (
    verify_broker_ping,
    verify_data_feed_freshness,
    run_cold_start_preflight,
    global_startup_watchdog,
)


@pytest.mark.asyncio
async def test_verify_broker_ping_success():
    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)
    client.get_account_info = AsyncMock(return_value={"equity": 10000.0, "login": 123456})

    assert await verify_broker_ping(client) is True


@pytest.mark.asyncio
async def test_verify_broker_ping_failure():
    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=False)

    assert await verify_broker_ping(client) is False


@pytest.mark.asyncio
async def test_verify_broker_ping_none_client():
    assert await verify_broker_ping(None) is False


@pytest.mark.asyncio
async def test_verify_data_feed_freshness():
    client = AsyncMock()
    now = time.time()

    async def mock_get_current_price(sym):
        if sym == "EURUSD":
            return {"ask": 1.0855, "bid": 1.0850, "fetched_at": now}
        elif sym == "USDJPY":
            # Stale quote (fetched 1 hour ago)
            return {"ask": 155.10, "bid": 155.08, "fetched_at": now - 3600}
        else:
            return None

    client.get_current_price = AsyncMock(side_effect=mock_get_current_price)

    res = await verify_data_feed_freshness(client, ["EURUSD", "USDJPY", "BTCUSD"], max_stale_sec=300.0)
    assert res["EURUSD"] is True
    assert res["USDJPY"] is False
    assert res["BTCUSD"] is False


@pytest.mark.asyncio
async def test_run_cold_start_preflight_success():
    mock_agent = MagicMock()
    mock_agent.dry_run = False
    mock_agent.settings = {"trading": {"asset_universe": ["EURUSD", "USDJPY"]}}

    mock_client = AsyncMock()
    mock_client.is_connected = AsyncMock(return_value=True)
    mock_client.get_account_info = AsyncMock(return_value={"equity": 10000.0})
    mock_client.get_current_price = AsyncMock(return_value={"ask": 1.085, "bid": 1.084, "fetched_at": time.time()})
    mock_agent.mt5_client = mock_client

    mock_exec = AsyncMock()
    mock_exec.sync_positions = AsyncMock()
    mock_exec.reconcile_inflight_orders = AsyncMock(return_value={"total": 0})
    mock_agent.execution_service = mock_exec

    summary = await run_cold_start_preflight(mock_agent)

    assert summary["broker_ping"] is True
    assert summary["positions_reconciled"] is True
    assert summary["ready"] is True
    mock_exec.sync_positions.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_cold_start_preflight_dry_run_resilient():
    # In dry_run mode, broker failure should not block startup
    mock_agent = MagicMock()
    mock_agent.dry_run = True
    mock_agent.settings = {"trading": {"asset_universe": ["EURUSD"]}}
    mock_agent.mt5_client = None
    mock_agent.execution_service = None

    summary = await run_cold_start_preflight(mock_agent)

    assert summary["broker_ping"] is True
    assert summary["positions_reconciled"] is True
    assert summary["ready"] is True
