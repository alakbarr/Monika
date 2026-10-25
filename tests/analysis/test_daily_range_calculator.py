from tests.conftest import create_mock_async_session
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context


class DummyRow:
    def __init__(self, time_str, open_p, high, low, close):
        self.timestamp = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
        self.open = open_p
        self.high = high
        self.low = low
        self.close = close


@pytest.mark.asyncio
async def test_compute_daily_range_context_normal_fx():
    # 5 days + today
    now = datetime.now(timezone.utc)
    today_str = now.isoformat()
    rows = [
        DummyRow(today_str, 1.0490, 1.0500, 1.0480, 1.0490),  # today: 0.0020
        DummyRow("2023-10-05T00:00:00", 1.04, 1.0520, 1.0420, 1.05),  # 0.0100
        DummyRow("2023-10-04T00:00:00", 1.04, 1.0480, 1.0380, 1.05),  # 0.0100
        DummyRow("2023-10-03T00:00:00", 1.04, 1.0550, 1.0450, 1.05),  # 0.0100
        DummyRow("2023-10-02T00:00:00", 1.04, 1.0600, 1.0500, 1.05),  # 0.0100
        DummyRow("2023-10-01T00:00:00", 1.04, 1.0500, 1.0400, 1.05),  # 0.0100
    ]

    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = rows
    mock_session.execute.return_value = mock_result

    settings = {
        "trading": {
            "risk": {
                "intraday_tp_min_adr_pct": 0.5,
                "intraday_tp_max_adr_pct": 0.8,
                "intraday_max_sl_adr_pct": 0.35,
            }
        }
    }

    res = await compute_daily_range_context(mock_session, "EURUSD", settings)
    assert res["adr"] == pytest.approx(0.0100)
    assert res["target_tp_min_distance"] == pytest.approx(0.0050)
    assert res["target_tp_max_distance"] == pytest.approx(0.0080)
    assert res["target_sl_max_distance"] == pytest.approx(0.0035)
    assert res["room_remaining_pct"] == pytest.approx(0.8)  # (1 - 0.0020/0.0100)
    assert res["lookback_days"] == 5


@pytest.mark.asyncio
async def test_compute_daily_range_context_crypto():
    now = datetime.now(timezone.utc)
    today_str = now.isoformat()
    rows = [
        DummyRow(today_str, 29000, 30000, 29500, 29800),  # 500
        DummyRow("2023-10-07T00:00:00", 29000, 30100, 29100, 30000),  # 1000
        DummyRow("2023-10-06T00:00:00", 29000, 30400, 29400, 30000),
        DummyRow("2023-10-05T00:00:00", 29000, 30200, 29200, 30000),
        DummyRow("2023-10-04T00:00:00", 29000, 29800, 28800, 30000),
        DummyRow("2023-10-03T00:00:00", 29000, 30500, 29500, 30000),
        DummyRow("2023-10-02T00:00:00", 29000, 31000, 30000, 30000),
        DummyRow("2023-10-01T00:00:00", 29000, 30000, 29000, 30000),
    ]
    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = rows
    mock_session.execute.return_value = mock_result

    settings = {}

    res = await compute_daily_range_context(mock_session, "BTCUSD", settings)
    assert res["adr"] == pytest.approx(1000.0)
    assert res["lookback_days"] == 7
    assert res["room_remaining_pct"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_compute_daily_range_context_insufficient_data():
    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result

    res = await compute_daily_range_context(mock_session, "EURUSD", {})
    assert "error" in res


@pytest.mark.asyncio
async def test_compute_daily_range_context_today_bar_not_written():
    rows = [
        DummyRow("2023-10-05T00:00:00", 1.04, 1.0520, 1.0420, 1.05),
        DummyRow("2023-10-04T00:00:00", 1.04, 1.0480, 1.0380, 1.05),
        DummyRow("2023-10-03T00:00:00", 1.04, 1.0550, 1.0450, 1.05),
        DummyRow("2023-10-02T00:00:00", 1.04, 1.0600, 1.0500, 1.05),
        DummyRow("2023-10-01T00:00:00", 1.04, 1.0500, 1.0400, 1.05),
    ]
    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = rows
    mock_session.execute.return_value = mock_result

    res = await compute_daily_range_context(mock_session, "EURUSD", {})
    assert res["room_remaining_pct"] == 1.0


@pytest.mark.asyncio
async def test_compute_daily_range_context_point_in_time_h1_prevents_d1_lookahead():
    """Verify that when as_of is passed mid-day, today_range_so_far uses H1 bars up to as_of instead of leaking the full 24h D1 bar."""
    as_of = datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc)
    d1_rows = [
        # Full-day D1 bar has huge 0.0200 range (leaking future NY session move after 13:00 UTC)
        DummyRow("2026-10-07T00:00:00", 1.1000, 1.1200, 1.1000, 1.1180),
        DummyRow("2026-10-06T00:00:00", 1.1000, 1.1100, 1.1000, 1.1050),
        DummyRow("2026-10-05T00:00:00", 1.1000, 1.1100, 1.1000, 1.1050),
        DummyRow("2026-10-04T00:00:00", 1.1000, 1.1100, 1.1000, 1.1050),
        DummyRow("2026-10-03T00:00:00", 1.1000, 1.1100, 1.1000, 1.1050),
        DummyRow("2026-10-02T00:00:00", 1.1000, 1.1100, 1.1000, 1.1050),
    ]
    h1_bar_1 = DummyRow("2026-10-07T08:00:00", 1.1000, 1.1020, 1.1000, 1.1015)
    h1_bar_1.timeframe = "H1"
    h1_bar_2 = DummyRow("2026-10-07T12:00:00", 1.1015, 1.1030, 1.1005, 1.1025)
    h1_bar_2.timeframe = "H1"

    def _exec_side_effect(stmt):
        res = MagicMock()
        q_str = str(stmt)
        if "H1" in q_str or "timestamp >=" in q_str:
            res.scalars().all.return_value = [h1_bar_1, h1_bar_2]
        else:
            res.scalars().all.return_value = d1_rows
        return res

    mock_session = create_mock_async_session()
    mock_session.execute = AsyncMock(side_effect=_exec_side_effect)

    res = await compute_daily_range_context(mock_session, "EURUSD", {}, as_of=as_of)
    assert res["adr"] == pytest.approx(0.0100)
    assert res["today_range_so_far"] == pytest.approx(0.0030)
    assert res["room_remaining_pct"] == pytest.approx(0.70)
    assert res["entry_allowed"] is True


def test_trimmed_average_and_volatility_regime_edges():
    from monika.application.analysis.calculators.daily_range_calculator import (
        _classify_volatility_regime,
        _trimmed_average,
    )

    assert _trimmed_average([]) == 0.0
    assert _trimmed_average([-5.0, "invalid"]) == 0.0
    assert _trimmed_average([10.0, 20.0, 30.0]) == pytest.approx(20.0)

    assert _classify_volatility_regime(1.0, 0.0) == ("normal", 1.0)
    assert _classify_volatility_regime(1.40, 1.0) == ("expanding_fast", 1.4)
    assert _classify_volatility_regime(1.20, 1.0) == ("expanding", 1.2)
    assert _classify_volatility_regime(0.60, 1.0) == ("contracting_fast", 0.6)
    assert _classify_volatility_regime(0.80, 1.0) == ("contracting", 0.8)
    assert _classify_volatility_regime(1.00, 1.0) == ("normal", 1.0)


@pytest.mark.asyncio
async def test_compute_baseline_adr_insufficient_valid_ranges():
    from monika.application.analysis.calculators.daily_range_calculator import _compute_baseline_adr

    # 10 rows total, but flat high == low so valid ranges < 8
    rows = [DummyRow(f"2026-09-{i:02d}T00:00:00", 1.1, 1.1, 1.1, 1.1) for i in range(1, 12)]
    mock_session = create_mock_async_session()
    mock_res = MagicMock()
    mock_res.scalars().all.return_value = rows
    mock_session.execute.return_value = mock_res

    res = await _compute_baseline_adr(mock_session, "EURUSD", 20, as_of=datetime(2026, 9, 20, tzinfo=timezone.utc))
    assert res is None


@pytest.mark.asyncio
async def test_compute_daily_range_context_error_and_room_branches():
    from unittest.mock import patch

    now = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    today_str = now.isoformat()

    # 1. Insufficient completed D1 history (3 rows total, today forming -> history_rows has 2 bars)
    rows_short_hist = [
        DummyRow(today_str, 1.10, 1.11, 1.10, 1.105),
        DummyRow("2026-10-06T00:00:00", 1.10, 1.11, 1.10, 1.105),
        DummyRow("2026-10-05T00:00:00", 1.10, 1.11, 1.10, 1.105),
    ]
    mock_session = create_mock_async_session()
    mock_res = MagicMock()
    mock_res.scalars().all.return_value = rows_short_hist
    mock_session.execute.return_value = mock_res

    err1 = await compute_daily_range_context(mock_session, "EURUSD", {}, as_of=now, lookback_days=4)
    assert "Insufficient completed D1 history" in err1["error"]

    # 2. No valid D1 ranges (high == low)
    rows_invalid_ranges = [
        DummyRow("2026-10-05T00:00:00", 1.10, 1.10, 1.10, 1.10),
        DummyRow("2026-10-04T00:00:00", 1.10, 1.10, 1.10, 1.10),
        DummyRow("2026-10-03T00:00:00", 1.10, 1.10, 1.10, 1.10),
    ]
    mock_res.scalars().all.return_value = rows_invalid_ranges
    err2 = await compute_daily_range_context(mock_session, "EURUSD", {}, as_of=now)
    assert "No valid D1 ranges" in err2["error"]

    # 3. Computed ADR <= 0 guard
    rows_valid = [
        DummyRow(today_str, 1.1000, 1.1080, 1.1000, 1.1070),  # 0.0080 (80% of ADR -> room 0.20)
        DummyRow("2026-10-06T00:00:00", 1.10, 1.11, 1.10, 1.105),
        DummyRow("2026-10-05T00:00:00", 1.10, 1.11, 1.10, 1.105),
        DummyRow("2026-10-04T00:00:00", 1.10, 1.11, 1.10, 1.105),
    ]
    mock_res.scalars().all.return_value = rows_valid
    with patch("monika.application.analysis.calculators.daily_range_calculator._trimmed_average", return_value=0.0):
        err3 = await compute_daily_range_context(mock_session, "EURUSD", {}, as_of=now)
        assert "Computed ADR <= 0" in err3["error"]

    # 4. TimesFM exception + room_remaining_pct = 0.20 ("reduced_target")
    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
        new_callable=AsyncMock,
        side_effect=RuntimeError("tfm unavailable"),
    ):
        res_reduced = await compute_daily_range_context(mock_session, "EURUSD", {}, as_of=now)
        assert res_reduced["session_recommendation"] == "reduced_target"
        assert res_reduced["entry_allowed"] is True

    # 5. TimesFM contracting ratio <= 0.75 + room_remaining_pct = 0.10 ("avoid_new_entry_low_room")
    rows_exhausted = [
        DummyRow(today_str, 1.1000, 1.1090, 1.1000, 1.1085),  # 0.0090 (90% of ADR -> room 0.10)
        DummyRow("2026-10-06T00:00:00", 1.10, 1.11, 1.10, 1.105),
        DummyRow("2026-10-05T00:00:00", 1.10, 1.11, 1.10, 1.105),
        DummyRow("2026-10-04T00:00:00", 1.10, 1.11, 1.10, 1.105),
    ]
    mock_res.scalars().all.return_value = rows_exhausted
    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
        new_callable=AsyncMock,
        return_value={"expected_range": 0.0070, "volatility_expansion_ratio": 0.65},
    ):
        res_avoid = await compute_daily_range_context(mock_session, "EURUSD", {}, as_of=now)
        assert res_avoid["volatility_regime"] == "contracting"
        assert res_avoid["session_recommendation"] == "avoid_new_entry_low_room"
        assert res_avoid["entry_allowed"] is False
