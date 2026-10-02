from tests.conftest import create_mock_async_session
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
import pandas as pd
from analysis.calculators.rolling_correlation_calculator import compute_rolling_correlation, compute_macro_cross_asset_matrix
from analysis.calculators.economic_surprise import compute_cesi_index


@pytest.mark.asyncio
async def test_rolling_correlation_computation():
    mock_session = create_mock_async_session()

    # Generate 40 daily bars for Symbol A and Symbol B with positive correlation
    dates = [datetime.now(timezone.utc) - timedelta(days=i) for i in reversed(range(40))]
    bars_a = []
    bars_b = []
    for i, d in enumerate(dates):
        p_a = 100.0 + (i * 1.5)
        p_b = 200.0 + (i * 3.0)  # strongly correlated

        b_a = MagicMock()
        b_a.timestamp = d
        b_a.close = p_a
        bars_a.append(b_a)

        b_b = MagicMock()
        b_b.timestamp = d
        b_b.close = p_b
        bars_b.append(b_b)

    exec_res_a = MagicMock()
    exec_res_a.scalars.return_value.all.return_value = bars_a

    exec_res_b = MagicMock()
    exec_res_b.scalars.return_value.all.return_value = bars_b

    mock_session.execute.side_effect = [exec_res_a, exec_res_b]

    res = await compute_rolling_correlation(mock_session, "XAUUSD", "DXY", window_days=20)
    assert res["symbol_a"] == "XAUUSD"
    assert res["symbol_b"] == "DXY"
    assert res["correlation_r"] > 0.8
    assert res["regime"] == "STRONG_POSITIVE"


@pytest.mark.asyncio
async def test_cesi_index_computation():
    mock_session = create_mock_async_session()

    # Generate mock EconomicCalendar events
    ev1 = MagicMock()
    ev1.event_time = datetime.now(timezone.utc) - timedelta(days=5)
    ev1.impact = "HIGH"
    ev1.surprise_score = 15.0

    ev2 = MagicMock()
    ev2.event_time = datetime.now(timezone.utc) - timedelta(days=20)
    ev2.impact = "MEDIUM"
    ev2.surprise_score = 10.0

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [ev1, ev2]
    mock_session.execute.return_value = mock_exec

    cesi = await compute_cesi_index(mock_session, "USD", window_days=90)
    assert cesi["currency"] == "USD"
    assert cesi["cesi_score"] > 5.0
    assert cesi["event_count"] == 2
