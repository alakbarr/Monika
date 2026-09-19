"""
Unit tests for Unified Cross-Surface Approval Hub & Steering Bus.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from risk.approval_hub import ApprovalHub, ApprovalRequest


@pytest.fixture(autouse=True)
def reset_approval_hub():
    """Reset singleton state before each test."""
    ApprovalHub._instance = None
    yield
    ApprovalHub._instance = None


@pytest.mark.asyncio
async def test_create_approval_request():
    hub = ApprovalHub.get_instance()
    req = hub.create_request(
        request_id="req_001",
        symbol="EURUSD",
        action="BUY",
        request_type="trade_proposal",
        details={"entry": 1.0850, "sl": 1.0810, "tp": 1.0920, "lot": 0.2},
    )

    assert req.request_id == "req_001"
    assert req.symbol == "EURUSD"
    assert req.action == "BUY"
    assert req.status == "pending"
    assert not req.is_expired
    assert len(hub.get_open_requests()) == 1


@pytest.mark.asyncio
async def test_approve_request_and_cross_surface_sync():
    hub = ApprovalHub.get_instance()
    events = []

    async def mock_listener(ev_type, data):
        events.append((ev_type, data))

    hub.register_listener(mock_listener)

    hub.create_request(
        request_id="req_002",
        symbol="XAUUSD",
        action="SELL",
        details={"analysis_id": 42},
    )

    # Approve from Telegram
    ok, msg = await hub.approve("req_002", operator="telegram:12345")
    assert ok is True
    assert "Approved" in msg

    req = hub._requests["req_002"]
    assert req.status == "approved"
    assert req.operator == "telegram:12345"

    # Verify open requests no longer includes approved item
    assert len(hub.get_open_requests()) == 0

    # Verify event broadcast
    assert any(ev[0] == "approval_resolved" and ev[1]["status"] == "approved" for ev in events)

    # Second approval attempt fails (prevent duplicate execution)
    ok2, msg2 = await hub.approve("req_002", operator="dashboard:admin")
    assert ok2 is False
    assert "already resolved" in msg2


@pytest.mark.asyncio
async def test_reject_request():
    hub = ApprovalHub.get_instance()
    hub.create_request(
        request_id="req_003",
        symbol="GBPUSD",
        action="BUY",
    )

    ok, msg = await hub.reject("req_003", operator="dashboard:operator", reason="Over-leveraged session")
    assert ok is True
    assert "Over-leveraged session" in msg

    req = hub._requests["req_003"]
    assert req.status == "rejected"
    assert req.operator == "dashboard:operator"
    assert req.rejection_reason == "Over-leveraged session"


@pytest.mark.asyncio
async def test_expired_request_handling():
    hub = ApprovalHub.get_instance()
    # Create request with expired timestamp
    req = hub.create_request(
        request_id="req_004",
        symbol="BTCUSD",
        action="BUY",
        ttl_minutes=-5,  # Already expired
    )

    assert req.is_expired is True
    assert len(hub.get_open_requests()) == 0

    ok, msg = await hub.approve("req_004", operator="telegram:123")
    assert ok is False
    assert "expired" in msg.lower()


@pytest.mark.asyncio
async def test_steer_synchronization():
    hub = ApprovalHub.get_instance()
    events = []

    async def mock_listener(ev_type, data):
        events.append((ev_type, data))

    hub.register_listener(mock_listener)

    payload = await hub.steer("EURUSD", "Focus on lower timeframe liquidity sweeps", operator="telegram:admin")
    assert payload["symbol"] == "EURUSD"
    assert payload["instruction"] == "Focus on lower timeframe liquidity sweeps"
    assert payload["operator"] == "telegram:admin"

    # Verify steer_injected broadcast
    assert any(ev[0] == "steer_injected" and ev[1]["instruction"] == "Focus on lower timeframe liquidity sweeps" for ev in events)
