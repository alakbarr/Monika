from tests.conftest import create_mock_async_session
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
        mock_session = create_mock_async_session()
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
        mock_session = create_mock_async_session()
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
        mock_session = create_mock_async_session()
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
        mock_session = create_mock_async_session()
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
        mock_session = create_mock_async_session()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_exec_res)

        resp = client.post("/api/actions/approve-trade/99999")
        assert resp.status_code == 404


def test_batch_close_positions(client):
    """Verify POST /api/actions/close-batch liquidates tickets."""
    mock_emergency = MagicMock()
    mock_emergency.close_positions_batch = AsyncMock(return_value={"closed": [101, 102], "success": True})
    set_dashboard_dependencies(emergency_manager=mock_emergency)

    payload = {"tickets": [101, 102], "reason": "Test emergency liquidation"}
    resp = client.post("/api/actions/close-batch", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    mock_emergency.close_positions_batch.assert_awaited_once_with(
        tickets=[101, 102],
        requested_by="dashboard_batch_close",
        reason="Test emergency liquidation",
    )


def test_manual_order_preview(client):
    """Verify POST /api/orders/preview returns risk and RR calculation."""
    payload = {
        "symbol": "EURUSD",
        "direction": "buy",
        "price": 1.0850,
        "sl": 1.0825,
        "tp": 1.0900,
        "volume": 0.2,
    }
    resp = client.post("/api/orders/preview", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "EURUSD"
    assert data["direction"] == "buy"
    assert data["volume"] == 0.2
    assert data["sl_distance_pips"] == 25.0
    assert data["tp_distance_pips"] == 50.0
    assert data["rr_ratio"] == 2.0


def test_manual_order_submit(client):
    """Verify POST /api/orders/submit executes order to MT5 and logs position."""
    mock_mt5 = MagicMock()
    mock_mt5.place_order = AsyncMock(return_value={"success": True, "ticket": 888777, "price": 1.0850})

    mock_verdict = MagicMock()
    mock_verdict.approved = True
    mock_risk_gate = MagicMock()
    mock_risk_gate.evaluate_proposal = AsyncMock(return_value=mock_verdict)

    set_dashboard_dependencies(mt5_client=mock_mt5, risk_gate=mock_risk_gate)


    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        payload = {
            "symbol": "EURUSD",
            "direction": "buy",
            "order_type": "buy",
            "volume": 0.1,
            "price": 1.0850,
            "sl": 1.0800,
            "tp": 1.0950,
            "comment": "Test:manual",
            "is_paper": False,
        }
        resp = client.post("/api/orders/submit", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["result"]["ticket"] == 888777
        assert data["is_paper"] is False
        mock_mt5.place_order.assert_awaited_once()


def test_manual_order_submit_paper(client):
    """Verify POST /api/orders/submit in paper mode isolates from MT5 broker."""
    mock_mt5 = MagicMock()
    mock_mt5.place_order = AsyncMock()

    mock_verdict = MagicMock()
    mock_verdict.approved = True
    mock_risk_gate = MagicMock()
    mock_risk_gate.evaluate_proposal = AsyncMock(return_value=mock_verdict)

    set_dashboard_dependencies(mt5_client=mock_mt5, risk_gate=mock_risk_gate)

    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        payload = {
            "symbol": "EURUSD",
            "direction": "buy",
            "order_type": "buy",
            "volume": 0.1,
            "price": 1.0850,
            "sl": 1.0800,
            "tp": 1.0950,
            "comment": "Test:paper",
            "is_paper": True,
        }
        resp = client.post("/api/orders/submit", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_paper"] is True
        assert data["result"]["is_paper"] is True
        mock_mt5.place_order.assert_not_awaited()


def test_market_candles_endpoint(client):
    """Verify GET /api/market/candles/{symbol} returns synthetic or live OHLCV bars."""
    resp = client.get("/api/market/candles/EURUSD?timeframe=H4&count=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "EURUSD"
    assert data["timeframe"] == "H4"
    assert len(data["candles"]) == 20
    assert "open" in data["candles"][0]
    assert "close" in data["candles"][0]


def test_market_structure_with_timesfm(client):
    """Verify GET /api/market/structure/{symbol} returns structure levels and timesfm cone."""
    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = create_mock_async_session()
        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_exec_res)
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        with patch("indicators.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock) as mock_fc:
            mock_fc.return_value = {
                "generated_at": "2026-10-06T12:00:00Z",
                "quantiles": {"q50": [1.086, 1.087]},
                "horizon_steps": 12,
            }
            resp = client.get("/api/market/structure/EURUSD?timeframe=H4")
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "EURUSD"
            assert "timesfm_cone" in data
            assert data["timesfm_cone"]["quantiles"]["q50"] == [1.086, 1.087]


def test_decision_dossier_endpoint(client):
    """Verify GET /api/analysis/decision-dossier/{analysis_id} returns 5-stage audit lineage."""
    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = create_mock_async_session()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        # Mock AssetAnalysis
        mock_analysis = MagicMock()
        mock_analysis.id = 42
        mock_analysis.symbol = "XAUUSD"
        mock_analysis.decision = "buy"
        mock_analysis.confidence = 0.85
        mock_analysis.entry_zone = "2650.5"
        mock_analysis.stop_loss = 2640.0
        mock_analysis.take_profit = 2675.0
        mock_analysis.invalidation_level = 2638.0
        mock_analysis.price_at_analysis = 2652.0
        mock_analysis.rationale = "Bullish liquidity sweep and FVG tap"
        mock_analysis.confluence_score = 82
        mock_analysis.priced_in_score = 25
        mock_analysis.ssvp_cds_score_at_analysis = 78.5
        mock_analysis.ssvp_suppressed = False
        mock_analysis.market_regime = "trending_bullish"
        mock_analysis.execution_status = "approved"
        mock_analysis.execution_notes = "RiskGate passed position sizing"
        mock_analysis.factors = ["FVG", "OB_H4", "RSI_DIV"]
        mock_analysis.macro_brief_summary = "Fed dovish tone supporting gold"
        mock_analysis.active_client_name = "gemini-2.5-pro"
        mock_analysis.debate_verdict = {
            "verdict": "buy",
            "modified": False,
            "bull_thesis": "Strong structure",
            "bear_thesis": "Overbought condition",
            "judge_reason": "Risk-reward asymmetry in favor of longs",
        }
        mock_analysis.created_at = None

        mock_session.get = AsyncMock(return_value=mock_analysis)

        # Mock queries for AssetAnalysis, Signal, Position, TradingCycleEventLog
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_scalars.all.return_value = []
        mock_exec = MagicMock()
        mock_exec.scalar_one_or_none.return_value = mock_analysis
        mock_exec.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_exec)

        resp = client.get("/api/analysis/decision-dossier/42")
        assert resp.status_code == 200
        dossier = resp.json()
        assert dossier["status"] == "success"
        assert dossier["analysis_id"] == 42
        assert dossier["symbol"] == "XAUUSD"
        assert dossier["decision"] == "buy"
        assert dossier["stage1_macro"]["risk_sentiment"] is not None
        assert dossier["stage2_tactical"]["confluence_score"] == 82
        assert dossier["stage3_debate"]["judge_verdict"] == "buy"
        assert dossier["stage4_riskgate"]["execution_status"] == "approved"
        assert dossier["stage5_execution"]["integrity_valid"] is True

