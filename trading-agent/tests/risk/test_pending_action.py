# ==============================================================================
# File: tests/risk/test_pending_action.py
# Monika 2-Phase Order Commit Protocol Test Suite
# ==============================================================================

import time
import pytest
from unittest.mock import AsyncMock

from risk.pending_action import (
    PendingActionManager,
    PendingActionStatus,
)


@pytest.fixture
def manager(tmp_path):
    return PendingActionManager(base_dir=tmp_path / "pending_orders")


def test_begin_action_and_get(manager):
    act = manager.begin_action(
        symbol="EURUSD",
        action="buy",
        volume=0.5,
        price=1.1050,
        sl=1.1000,
        tp=1.1150,
        comment="test_order",
    )
    assert act.symbol == "EURUSD"
    assert act.action == "buy"
    assert act.volume == 0.5
    assert act.status == PendingActionStatus.DISPATCHING

    # Retrieve from disk
    stored = manager.get_action(act.client_order_id)
    assert stored is not None
    assert stored.client_order_id == act.client_order_id
    assert stored.status == PendingActionStatus.DISPATCHING


def test_commit_action(manager):
    act = manager.begin_action(symbol="XAUUSD", action="sell", volume=0.1)
    committed = manager.commit_action(act.client_order_id, broker_ticket=12345678)
    assert committed is not None
    assert committed.status == PendingActionStatus.COMMITTED
    assert committed.broker_ticket == 12345678

    stored = manager.get_action(act.client_order_id)
    assert stored.status == PendingActionStatus.COMMITTED
    assert stored.broker_ticket == 12345678


def test_fail_and_unconfirmed_action(manager):
    act1 = manager.begin_action(symbol="BTCUSD", action="buy", volume=0.01)
    failed = manager.fail_action(act1.client_order_id, "Market closed")
    assert failed.status == PendingActionStatus.FAILED
    assert failed.error_message == "Market closed"

    act2 = manager.begin_action(symbol="USDJPY", action="buy", volume=0.2)
    unconf = manager.mark_unconfirmed(act2.client_order_id, "Socket timeout 3s")
    assert unconf.status == PendingActionStatus.UNCONFIRMED_DISPATCH

    # Check unconfirmed list
    unconfirmed = manager.get_unconfirmed_actions()
    unconfirmed_ids = [a.client_order_id for a in unconfirmed]
    assert act1.client_order_id not in unconfirmed_ids
    assert act2.client_order_id in unconfirmed_ids


@pytest.mark.asyncio
async def test_reconcile_at_boot_found_in_positions(manager):
    act = manager.begin_action(symbol="EURUSD", action="buy", volume=0.5, comment="AIAgent_nonce123")
    
    mock_mt5 = AsyncMock()
    # Return matching position
    mock_mt5.get_open_positions.return_value = [
        {
            "ticket": 998877,
            "symbol": "EURUSD",
            "type": "buy",
            "volume": 0.5,
            "comment": f"test_{act.nonce}",
            "time": time.time(),
        }
    ]

    results = await manager.reconcile_at_boot(mock_mt5)
    assert len(results) == 1
    assert results[0]["status"] == "RECONCILED_COMMITTED"
    assert results[0]["ticket"] == 998877

    stored = manager.get_action(act.client_order_id)
    assert stored.status == PendingActionStatus.COMMITTED


@pytest.mark.asyncio
async def test_reconcile_at_boot_expired_unmatched(manager):
    act = manager.begin_action(symbol="GBPUSD", action="buy", volume=0.2)
    # Artificially set timestamp to 200s ago
    act.timestamp = time.time() - 200.0
    manager._atomic_write_action(act)

    mock_mt5 = AsyncMock()
    mock_mt5.get_open_positions.return_value = []

    results = await manager.reconcile_at_boot(mock_mt5)
    assert len(results) == 1
    assert results[0]["status"] == "RECONCILED_FAILED"

    stored = manager.get_action(act.client_order_id)
    assert stored.status == PendingActionStatus.FAILED
