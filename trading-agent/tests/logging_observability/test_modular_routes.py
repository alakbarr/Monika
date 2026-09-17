# ==============================================================================
# File: tests/logging_observability/test_modular_routes.py
# Description: Tests for Modular Dashboard Routers Structure & Integration
# ==============================================================================

import pytest
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import app
from logging_observability.dashboard.routes import (
    all_routers,
    system_router,
    tokens_router,
    config_router,
    trading_router,
    observability_router,
    websocket_router,
    trace_search_router,
    set_dashboard_dependencies,
    get_dashboard_dependency,
    _safe_json,
    TriggerCycleRequest,
    OverrideRiskRequest,
    ClosePositionRequest,
)


def test_modular_routers_exported_and_mounted():
    """Verify all 7 routers are properly populated and included in all_routers."""
    assert len(all_routers) == 7
    assert system_router in all_routers
    assert tokens_router in all_routers
    assert config_router in all_routers
    assert trading_router in all_routers
    assert observability_router in all_routers
    assert websocket_router in all_routers
    assert trace_search_router in all_routers


def test_dependency_injection_registry():
    """Verify dashboard dependency registration and retrieval."""
    mock_obj = object()
    set_dashboard_dependencies(test_dep=mock_obj)
    assert get_dashboard_dependency("test_dep") is mock_obj
    assert get_dashboard_dependency("non_existent") is None


def test_safe_json_utility():
    """Verify _safe_json parses valid json and safely returns string or None."""
    assert _safe_json(None) is None
    assert _safe_json('{"key": "value"}') == {"key": "value"}
    assert _safe_json("[1, 2, 3]") == [1, 2, 3]
    assert _safe_json("invalid-json{") == "invalid-json{"


def test_request_models_validation():
    """Verify TriggerCycleRequest, OverrideRiskRequest, ClosePositionRequest instantiation."""
    cycle_req = TriggerCycleRequest(forced=True, reason="Unit test")
    assert cycle_req.forced is True
    assert cycle_req.reason == "Unit test"

    risk_req = OverrideRiskRequest(risk_percent_per_trade=1.5, max_daily_drawdown_percent=5.0)
    assert risk_req.risk_percent_per_trade == 1.5
    assert risk_req.max_daily_drawdown_percent == 5.0

    close_req = ClosePositionRequest(ticket=12345, reason="Testing close")
    assert close_req.ticket == 12345
    assert close_req.reason == "Testing close"


def test_ping_endpoint_via_testclient():
    """Verify /api/ping responds via TestClient."""
    client = TestClient(app)
    response = client.get("/api/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pong"
    assert "timestamp" in data


def test_context_tracker_endpoint():
    """Verify /api/v1/tokens/context-tracker responds with accumulator metrics."""
    client = TestClient(app)
    response = client.get("/api/v1/tokens/context-tracker")
    assert response.status_code == 200
    data = response.json()
    assert "used_tokens" in data
    assert "max_context_window" in data
    assert "utilization_ratio" in data


def test_steer_endpoint():
    """Verify /api/actions/steer accepts SteerRequest and records directive."""
    client = TestClient(app)
    response = client.post(
        "/api/actions/steer",
        json={"message": "Focus on DXY correlation during NFP", "mode": "steer", "symbols": ["EURUSD"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "steered"
    assert data["mode"] == "steer"
