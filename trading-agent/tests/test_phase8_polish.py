"""Unit tests for Phase 8 medium improvements and polish."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from risk.correlation_matrix import DynamicCorrelationMatrix
from scheduler.position_supervisor import PositionSupervisor
from utils.llm.credential_pool import CredentialPool, CredentialState


def test_dynamic_correlation_matrix_pearson():
    series_a = [1.0, 2.0, 3.0, 4.0, 5.0]
    series_b = [2.0, 4.0, 6.0, 8.0, 10.0]
    corr = DynamicCorrelationMatrix.calculate_pearson_correlation(series_a, series_b)
    assert corr == 1.0

    series_c = [-1.0, -2.0, -3.0, -4.0, -5.0]
    corr_neg = DynamicCorrelationMatrix.calculate_pearson_correlation(series_a, series_c)
    assert corr_neg == -1.0


def test_dynamic_correlation_portfolio_heat():
    engine = DynamicCorrelationMatrix(correlation_threshold=0.6)
    matrix = {
        "EURUSD": {"EURUSD": 1.0, "GBPUSD": 0.85},
        "GBPUSD": {"EURUSD": 0.85, "GBPUSD": 1.0},
    }
    positions = [
        {"symbol": "EURUSD", "direction": "BUY", "volume": 0.1},
        {"symbol": "GBPUSD", "direction": "BUY", "volume": 0.1},
    ]
    heat = engine.calculate_portfolio_heat(positions, matrix)
    assert len(heat["correlated_pairs"]) == 1
    assert heat["correlated_pairs"][0]["pair"] == "EURUSD/GBPUSD"
    assert heat["portfolio_heat"] > 0


@pytest.mark.asyncio
async def test_position_supervisor_dispatch():
    mock_mt5 = MagicMock()
    mock_mt5.is_connected = AsyncMock(return_value=True)
    mock_mt5.get_open_positions = AsyncMock(return_value=[{"ticket": 1234, "symbol": "EURUSD"}])
    mock_mt5.get_account_info = AsyncMock(return_value={"balance": 10000.0, "equity": 10050.0})

    supervisor = PositionSupervisor(mt5_client=mock_mt5, poll_interval_seconds=1.0)

    received_eval = []
    async def evaluator_callback(positions, account):
        received_eval.append((positions, account))

    supervisor.register_evaluator("test_evaluator", evaluator_callback)
    await supervisor.poll_once()

    assert len(received_eval) == 1
    positions, account = received_eval[0]
    assert len(positions) == 1
    assert positions[0]["ticket"] == 1234
    assert account["balance"] == 10000.0


@pytest.mark.asyncio
async def test_credential_pool_rotation_and_cooldown():
    pool = CredentialPool(provider="gemini", keys=["key1", "key2"])
    assert pool.total_keys() == 2

    k1 = await pool.get_active_key()
    assert k1 in ("key1", "key2")

    # Mark key1 as rate limited
    await pool.report_rate_limited(k1, cooldown_seconds=10.0)

    k2 = await pool.get_active_key()
    # Must yield the other key
    assert k2 != k1


@pytest.mark.asyncio
async def test_risk_gate_check_correlation_exposure():
    from risk.risk_gate import RiskGate

    mock_settings = {
        "trading": {
            "risk": {
                "correlation_limit": 3,
                "correlation_threshold": 0.65,
                "max_lot_per_symbol": 1.0,
            }
        },
        "paper_trading": {"initial_balance": 10000.0},
    }
    gate = RiskGate(mock_settings)
    mock_session = AsyncMock()

    # Empty positions -> pass
    ok, reason = await gate.check_correlation_exposure(mock_session, "EURUSD", "buy", open_positions=[])
    assert ok
    assert "no existing positions" in reason

    # Simulated positions with high correlation
    pos = {"symbol": "GBPUSD", "direction": "buy", "volume": 1.0}
    gate._get_dynamic_correlation = AsyncMock(return_value=(0.85, 0.01))
    
    # Exceed limit: 1.0 + 4 * 0.85 = 4.4 > 3
    ok, reason = await gate.check_correlation_exposure(
        mock_session, "EURUSD", "buy", open_positions=[pos, pos, pos, pos]
    )
    assert not ok
    assert "Correlated exposure limit exceeded" in reason

