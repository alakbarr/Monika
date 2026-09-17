"""
Unit tests for Interactive 2-Way Dashboard Control Endpoints (MED-02).
Tests /api/actions/trigger-cycle, /api/actions/override-risk,
/api/actions/close-position, and /api/actions/approve-trade/{id}.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import (
    app,
    set_dashboard_dependencies,
    _dependencies,
)


@pytest.fixture
def client():
    # Clear and prepare dependencies
    _dependencies.clear()
    return TestClient(app)


def test_trigger_cycle_success(client):
    """Verify POST /api/actions/trigger-cycle dispatches cycle when scheduler ready."""
    mock_cycle_sched = MagicMock()
    mock_cycle_sched._cycle_lock = MagicMock()
    mock_cycle_sched._cycle_lock.locked.return_value = False
    mock_cycle_sched.run_once = AsyncMock(return_value={"status": "executed"})

    set_dashboard_dependencies(cycle_scheduler=mock_cycle_sched)

    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        resp = client.post("/api/actions/trigger-cycle", json={"forced": True, "reason": "Operator request"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        assert data["forced"] is True


def test_trigger_cycle_already_running(client):
    """Verify POST /api/actions/trigger-cycle returns 409 Conflict if cycle lock is held."""
    mock_cycle_sched = MagicMock()
    mock_cycle_sched._cycle_lock = MagicMock()
    mock_cycle_sched._cycle_lock.locked.return_value = True

    set_dashboard_dependencies(cycle_scheduler=mock_cycle_sched)

    resp = client.post("/api/actions/trigger-cycle", json={"forced": True})
    assert resp.status_code == 409
    assert "already actively executing" in resp.json()["message"]


def test_trigger_cycle_unavailable(client):
    """Verify POST /api/actions/trigger-cycle returns 503 if cycle scheduler is not registered."""
    resp = client.post("/api/actions/trigger-cycle", json={"forced": True})
    assert resp.status_code == 503


def test_override_risk_parameters(client):
    """Verify POST /api/actions/override-risk updates SystemConfig and runtime settings."""
    settings = {"trading": {"risk": {"risk_percent_per_trade": 1.0}}}
    set_dashboard_dependencies(settings=settings)

    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        # Mock no existing row
        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_exec_res)

        payload = {
            "risk_percent_per_trade": 0.5,
            "max_daily_drawdown_percent": 2.5,
            "max_concurrent_positions": 3,
        }
        resp = client.post("/api/actions/override-risk", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["updated"]["risk_percent_per_trade"] == 0.5
        assert data["updated"]["max_concurrent_positions"] == 3
        # In-memory settings updated
        assert settings["trading"]["risk"]["risk_percent_per_trade"] == 0.5


def test_override_risk_empty_payload(client):
    """Verify POST /api/actions/override-risk rejects empty payload with 400."""
    resp = client.post("/api/actions/override-risk", json={})
    assert resp.status_code == 400


def test_close_position_by_ticket(client):
    """Verify POST /api/actions/close-position closes position via ExecutionService."""
    mock_exec_svc = MagicMock()
    mock_exec_svc.close_position_by_ticket = AsyncMock(return_value={"success": True, "profit": 150.0})
    set_dashboard_dependencies(execution_service=mock_exec_svc)

    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        resp = client.post("/api/actions/close-position", json={"ticket": 123456, "reason": "Take Profit"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["ticket"] == 123456
        mock_exec_svc.close_position_by_ticket.assert_awaited_once_with(
            ticket=123456,
            requested_by="dashboard",
            reason="Take Profit",
        )


def test_close_position_missing_identifier(client):
    """Verify POST /api/actions/close-position returns 400 if neither ticket nor position_id provided."""
    resp = client.post("/api/actions/close-position", json={"reason": "Manual"})
    assert resp.status_code == 400


def test_approve_trade_trigger(client):
    """Verify POST/PUT /api/actions/approve-trade/{id} approves a TradeTrigger."""
    from database.models import TradeTrigger

    mock_trigger = TradeTrigger(
        id=99,
        asset_analysis_id=1,
        trigger_type="limit_order",
        status="pending",
    )

    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.return_value = mock_trigger
        mock_session.execute = AsyncMock(return_value=mock_exec_res)

        resp = client.post("/api/actions/approve-trade/99")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["type"] == "TradeTrigger"
        assert mock_trigger.status == "approved"


def test_approve_trade_not_found(client):
    """Verify POST /api/actions/approve-trade/{id} returns 404 if ID does not match any record."""
    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_exec_res)

        resp = client.post("/api/actions/approve-trade/99999")
        assert resp.status_code == 404
