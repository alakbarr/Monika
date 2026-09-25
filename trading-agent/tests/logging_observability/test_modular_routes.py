# ==============================================================================
# File: tests/logging_observability/test_modular_routes.py
# Description: Tests for Modular Dashboard Routers Structure & Integration
# ==============================================================================

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
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
    backtest_router,
    memory_router,
    intelligence_router,
    plugins_router,
    benchmark_router,
    set_dashboard_dependencies,
    get_dashboard_dependency,
    _safe_json,
    TriggerCycleRequest,
    OverrideRiskRequest,
    ClosePositionRequest,
    ModifyPositionRequest,
)


def test_modular_routers_exported_and_mounted():
    """Verify all 12 routers are properly populated and included in all_routers."""
    assert len(all_routers) == 12
    assert system_router in all_routers
    assert tokens_router in all_routers
    assert config_router in all_routers
    assert trading_router in all_routers
    assert observability_router in all_routers
    assert websocket_router in all_routers
    assert trace_search_router in all_routers
    assert backtest_router in all_routers
    assert memory_router in all_routers
    assert intelligence_router in all_routers
    assert plugins_router in all_routers
    assert benchmark_router in all_routers


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
    with patch("database.db.AsyncSessionLocal") as mock_sess_cls:
        mock_session = AsyncMock()
        mock_sess_cls.return_value.__aenter__.return_value = mock_session
        response = client.post(
            "/api/actions/steer",
            json={"message": "Focus on DXY correlation during NFP", "mode": "steer", "symbols": ["EURUSD"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "steered"
        assert data["mode"] == "steer"


def test_calendar_upcoming_endpoint():
    """Verify /api/calendar/upcoming responds with event list."""
    client = TestClient(app)
    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_sess_cls:
        mock_session = AsyncMock()
        mock_sess_cls.return_value.__aenter__.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        response = client.get("/api/calendar/upcoming")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_skills_catalog_endpoint():
    """Verify /api/skills responds with skills list."""
    client = TestClient(app)
    with patch("logging_observability.dashboard.routes.intelligence.list_skills", return_value=["test_skill"]):
        with patch("logging_observability.dashboard.routes.intelligence.get_skill_metadata", return_value={"description": "Test"}):
            response = client.get("/api/skills")
            assert response.status_code == 200
            data = response.json()
            assert "skills" in data
            assert data["total"] == 1


def test_modify_position_request_model():
    """Verify ModifyPositionRequest instantiation."""
    req = ModifyPositionRequest(sl=1.0550, tp=1.0850, comment="Test update")
    assert req.sl == 1.0550
    assert req.tp == 1.0850
    assert req.comment == "Test update"


def test_modify_position_endpoint():
    """Verify POST /api/positions/{ticket}/modify updates position SL/TP."""
    client = TestClient(app)
    with patch("database.db.AsyncSessionLocal") as mock_sess_cls:
        mock_session = AsyncMock()
        mock_sess_cls.return_value.__aenter__.return_value = mock_session

        mock_pos = MagicMock()
        mock_pos.id = 1
        mock_pos.mt5_ticket = 99999
        mock_pos.sl = 1.0500
        mock_pos.tp = 1.0800

        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = mock_pos
        mock_session.execute = AsyncMock(return_value=mock_res)
        mock_session.commit = AsyncMock()

        response = client.post(
            "/api/positions/99999/modify",
            json={"sl": 1.0550, "tp": 1.0850, "comment": "Tighter SL"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert mock_pos.sl == 1.0550
        assert mock_pos.tp == 1.0850


def test_market_indicators_endpoint():
    """Verify GET /api/market/indicators/{symbol} returns snapshot."""
    client = TestClient(app)
    with patch("database.db.AsyncSessionLocal") as mock_sess_cls:
        mock_session = AsyncMock()
        mock_sess_cls.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_res)

        with patch("indicators.technical.TechnicalIndicatorCalculator.get_snapshot", return_value={"RSI_14": 55.4}):
            response = client.get("/api/market/indicators/EURUSD?timeframe=H1")
            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == "EURUSD"
            assert data["timeframe"] == "H1"
            assert "indicators" in data


def test_market_structure_endpoint():
    """Verify GET /api/market/structure/{symbol} returns structure levels."""
    client = TestClient(app)
    with patch("database.db.AsyncSessionLocal") as mock_sess_cls:
        mock_session = AsyncMock()
        mock_sess_cls.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/market/structure/EURUSD?timeframe=H4")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["timeframe"] == "H4"
        assert "order_blocks" in data
        assert "structure_breaks" in data
        assert "fair_value_gaps" in data


def test_trade_trajectories_endpoint():
    """Verify GET /api/observability/trajectories returns records from TradeTrajectoryLogger."""
    client = TestClient(app)
    with patch("benchmark.trade_trajectory_logger.TradeTrajectoryLogger.load_recent_trajectories", return_value=[
        {"symbol": "EURUSD", "decision": "BUY", "ticket": 12345, "timestamp": "2026-09-24T00:00:00Z"}
    ]):
        response = client.get("/api/observability/trajectories?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["trajectories"]) == 1
        assert data["trajectories"][0]["symbol"] == "EURUSD"


def test_cycle_decision_lineage_endpoint():
    """Verify GET /api/observability/cycles/{cycle_id}/lineage returns event provenance and integrity."""
    client = TestClient(app)
    mock_event_log = MagicMock()
    mock_event_log.reconstruct_cycle.return_value = {
        "cycle_id": "cycle-test-1",
        "total_events": 2,
        "events": [
            {"seq": 1, "event_type": "cycle/start", "chain_hash": "hash1"},
            {"seq": 2, "event_type": "order/fill", "chain_hash": "hash2", "source_event_seqs": [1]}
        ],
        "start_time": "2026-09-24T00:00:00Z",
        "end_time": "2026-09-24T00:05:00Z",
    }
    mock_event_log.verify_cycle_integrity.return_value = (True, None)
    mock_event_log.trace_decision_lineage.return_value = []

    with patch("logging_observability.trading_cycle_event_log.get_cycle_event_log", return_value=mock_event_log):
        response = client.get("/api/observability/cycles/cycle-test-1/lineage?target_seq=2")
        assert response.status_code == 200
        data = response.json()
        assert data["cycle_id"] == "cycle-test-1"
        assert data["integrity_valid"] is True
        assert data["total_events"] == 2


