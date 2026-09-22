"""
Unit tests for Backtest Dashboard API endpoints (/api/backtest/*).
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

from logging_observability.dashboard.api import app
from database.models import BacktestRun, BacktestTrade

client = TestClient(app)


def test_list_backtest_runs():
    """Verify GET /api/backtest/runs returns list of historical backtest runs."""
    mock_run = BacktestRun(
        id=1,
        mode="full",
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        step_hours=6,
        initial_equity=10000.0,
        final_equity=11250.0,
        total_trades=20,
        win_rate=65.0,
        profit_factor=2.1,
        sharpe_ratio=1.85,
        max_drawdown_pct=4.2,
        created_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_run]
    mock_session.execute = AsyncMock(return_value=mock_res)

    with patch("logging_observability.dashboard.routes.backtest.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session

        resp = client.get("/api/backtest/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["runs"]) == 1
        assert data["runs"][0]["id"] == 1
        assert data["runs"][0]["mode"] == "full"
        assert data["runs"][0]["win_rate"] == 65.0


def test_get_backtest_run_details():
    """Verify GET /api/backtest/runs/{run_id} returns run telemetry and associated trades."""
    mock_run = BacktestRun(
        id=42,
        mode="replay",
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        step_hours=6,
        initial_equity=10000.0,
        final_equity=10500.0,
        total_trades=1,
        win_rate=100.0,
        profit_factor=99.0,
        sharpe_ratio=2.4,
        max_drawdown_pct=1.5,
        created_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )

    mock_trade = BacktestTrade(
        id=101,
        run_id=42,
        symbol="EURUSD",
        direction="buy",
        entry_time=datetime(2026, 1, 5, tzinfo=timezone.utc),
        entry_price=1.1000,
        exit_time=datetime(2026, 1, 5, 4, tzinfo=timezone.utc),
        exit_price=1.1050,
        exit_reason="tp_hit",
        pnl_pips=50.0,
        pnl_pct=5.0,
        executed_lots=0.5,
        confidence=85.0,
        rationale="Confluence test",
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_run)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_trade]
    mock_session.execute = AsyncMock(return_value=mock_res)

    with patch("logging_observability.dashboard.routes.backtest.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session

        resp = client.get("/api/backtest/runs/42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["id"] == 42
        assert data["trades_count"] == 1
        assert data["trades"][0]["symbol"] == "EURUSD"
        assert data["trades"][0]["pnl_pct"] == 5.0


def test_trigger_backtest_run():
    """Verify POST /api/backtest/run queues a background backtest execution."""
    resp = client.post(
        "/api/backtest/run",
        json={"days": 14, "mode": "full", "initial_equity": 20000.0, "step_hours": 4},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert "14 days" in data["message"]
