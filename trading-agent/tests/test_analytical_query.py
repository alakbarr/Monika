import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from analysis.tools.handlers.analytical_query_builder import handle_run_analytical_query
from analysis.calculators.rolling_correlation_calculator import compute_rolling_correlation


@pytest.mark.asyncio
async def test_analytical_query_builder_overview():
    # Mock session
    mock_session = AsyncMock()

    # Mock TradeOutcome scalars
    mock_outcome_1 = MagicMock()
    mock_outcome_1.id = 1
    mock_outcome_1.symbol = "EURUSD"
    mock_outcome_1.direction = "buy"
    mock_outcome_1.pnl_usd = 150.0
    mock_outcome_1.entry_price = 1.0800
    mock_outcome_1.stop_loss = 1.0750
    mock_outcome_1.take_profit = 1.0900
    mock_outcome_1.holding_hours = 4.5
    mock_outcome_1.mae_pips = 10.0
    mock_outcome_1.mfe_pips = 100.0
    mock_outcome_1.sl_slippage_pips = 0.0
    mock_outcome_1.entry_session = "London"
    mock_outcome_1.market_regime = "TRENDING"
    mock_outcome_1.decision_source = "LLM_Agent"
    mock_outcome_1.closed_at = datetime.now(timezone.utc)

    mock_outcome_2 = MagicMock()
    mock_outcome_2.id = 2
    mock_outcome_2.symbol = "EURUSD"
    mock_outcome_2.direction = "sell"
    mock_outcome_2.pnl_usd = -50.0
    mock_outcome_2.entry_price = 1.0850
    mock_outcome_2.stop_loss = 1.0900
    mock_outcome_2.take_profit = 1.0750
    mock_outcome_2.holding_hours = 2.0
    mock_outcome_2.mae_pips = 50.0
    mock_outcome_2.mfe_pips = 10.0
    mock_outcome_2.sl_slippage_pips = 1.2
    mock_outcome_2.entry_session = "NewYork"
    mock_outcome_2.market_regime = "VOLATILE_CHOP"
    mock_outcome_2.decision_source = "LLM_Agent"
    mock_outcome_2.closed_at = datetime.now(timezone.utc)

    mock_exec_res_outcomes = MagicMock()
    mock_exec_res_outcomes.scalars.return_value.all.return_value = [mock_outcome_1, mock_outcome_2]

    mock_exec_res_pos = MagicMock()
    mock_exec_res_pos.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_exec_res_outcomes, mock_exec_res_pos]

    res = await handle_run_analytical_query(
        {"metric": "overview", "group_by": "session", "days_back": 30},
        session=mock_session
    )

    assert res["metric"] == "overview"
    assert res["group_by"] == "session"
    assert "breakdown" in res
    assert "London" in res["breakdown"]
    assert res["breakdown"]["London"]["won"] == 1
    assert res["breakdown"]["London"]["win_rate_pct"] == 100.0
    assert "NewYork" in res["breakdown"]
    assert res["breakdown"]["NewYork"]["lost"] == 1
