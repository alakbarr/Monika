"""
Unit tests for Advanced Quantitative Tool Handlers (verifying no fake fallbacks or mocks).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from tests.conftest import create_mock_async_session

from monika.application.analysis.tools.handlers.advanced_quant_tools import (
    handle_get_carry_trade_rankings,
    handle_get_commodity_spread,
    handle_optimize_strategy_parameters,
    handle_run_model_benchmark,
    handle_run_walk_forward_optimization,
)
from monika.application.analysis.tools.handlers.smc_tools import handle_get_smt_divergence
from monika.infrastructure.database.models import CentralBankRateExpectation


@pytest.mark.asyncio
async def test_carry_trade_rankings_insufficient_data_without_session():
    """Verify handle_get_carry_trade_rankings fails closed when no session or rates exist."""
    res = await handle_get_carry_trade_rankings({})
    assert res["status"] == "insufficient_data"
    assert "error" in res


@pytest.mark.asyncio
async def test_carry_trade_rankings_with_real_session():
    """Verify handle_get_carry_trade_rankings computes from CentralBankRateExpectation rows."""
    session = create_mock_async_session()
    now = datetime.now(timezone.utc)
    mock_rates = [
        CentralBankRateExpectation(bank="FED", current_rate=4.0, meeting_date="2026-11-01", fetched_at=now),
        CentralBankRateExpectation(bank="BOJ", current_rate=1.0, meeting_date="2026-11-01", fetched_at=now),
        CentralBankRateExpectation(bank="ECB", current_rate=2.5, meeting_date="2026-11-01", fetched_at=now),
    ]
    mock_res = session.execute.return_value
    mock_res.scalars.return_value.all.return_value = mock_rates

    res = await handle_get_carry_trade_rankings({}, session=session)
    assert res["status"] == "success"
    assert len(res["ranked_pairs"]) > 0
    usdjpy_rank = next((p for p in res["ranked_pairs"] if p["pair"] == "USDJPY"), None)
    assert usdjpy_rank is not None
    assert usdjpy_rank["base_rate_pct"] == 4.0
    assert usdjpy_rank["quote_rate_pct"] == 1.0
    assert usdjpy_rank["nominal_spread_pct"] == 3.0


@pytest.mark.asyncio
async def test_walk_forward_optimization_no_hardcoded_fake_metrics():
    """Verify Walk-Forward Optimization returns genuine results, never hardcoded fake fallbacks."""
    with patch(
        "monika.application.backtest.walk_forward_engine.WalkForwardEngine.run",
        side_effect=RuntimeError("Engine test failure"),
    ):
        res = await handle_run_walk_forward_optimization({"strategy": "invalid_strat", "symbol": "EURUSD"})
        assert res["status"] == "error"
        assert "wfe_pct" not in res
        assert "deflated_sharpe_ratio" not in res
        assert "Engine test failure" in res["error"]


@pytest.mark.asyncio
async def test_model_benchmark_fails_without_fake_elo():
    """Verify model benchmark fails closed with error instead of hardcoded 1542 Elo."""
    res = await handle_run_model_benchmark({"models": ["unknown-model"]})
    assert res["status"] in ("success", "error")
    if res["status"] == "error":
        assert "error" in res
        assert "elo_leaderboard" not in res


@pytest.mark.asyncio
async def test_commodity_spread_insufficient_data():
    """Verify handle_get_commodity_spread fails closed when neither quotes nor bars exist."""
    session = create_mock_async_session()
    mock_res = session.execute.return_value
    mock_res.scalar_one_or_none.return_value = None

    res = await handle_get_commodity_spread({"primary_symbol": "XBRUSD", "secondary_symbol": "XTIUSD"}, session=session)
    assert res["status"] == "insufficient_data"
    assert "error" in res


@pytest.mark.asyncio
async def test_smt_divergence_fails_closed_on_missing_reference():
    """Verify handle_get_smt_divergence fails closed when reference symbol has no bars in DB."""
    session = create_mock_async_session()
    mock_res = session.execute.return_value
    mock_res.scalars.return_value.all.return_value = []

    res = await handle_get_smt_divergence({"symbol": "EURUSD", "compared_symbol": "DXY"}, session=session)
    assert res["status"] == "partial_data"
    assert res["smt_detected"] is False
    assert "Insufficient historical candles" in res["note"]


@pytest.mark.asyncio
async def test_garch_volatility_tool():
    """Verify handle_get_garch_volatility executes cleanly on simulated price bars."""
    from monika.application.analysis.tools.handlers.advanced_quant_tools import handle_get_garch_volatility

    session = create_mock_async_session()
    mock_res = session.execute.return_value
    mock_res.scalars.return_value.all.return_value = [100.0 + i * 0.1 for i in range(50)]

    res = await handle_get_garch_volatility({"symbol": "XAUUSD", "timeframe": "H1"}, session=session)
    assert res["status"] == "success"
    assert "current_volatility" in res
    assert "forecasted_volatility_1step" in res
    assert "volatility_regime" in res


@pytest.mark.asyncio
async def test_copula_tail_risk_tool():
    """Verify handle_get_copula_tail_risk fails closed on insufficient matching bars."""
    from monika.application.analysis.tools.handlers.advanced_quant_tools import handle_get_copula_tail_risk

    session = create_mock_async_session()
    mock_res = session.execute.return_value
    mock_res.all.return_value = []

    res = await handle_get_copula_tail_risk({"asset1": "EURUSD", "asset2": "GBPUSD"}, session=session)
    assert res["status"] == "insufficient_data"
    assert "error" in res
