import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from analysis.calculators.daily_range_calculator import compute_daily_range_context

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
        DummyRow(today_str, 1.0490, 1.0500, 1.0480, 1.0490), # today: 0.0020
        DummyRow("2023-10-05T00:00:00", 1.04, 1.0520, 1.0420, 1.05), # 0.0100
        DummyRow("2023-10-04T00:00:00", 1.04, 1.0480, 1.0380, 1.05), # 0.0100
        DummyRow("2023-10-03T00:00:00", 1.04, 1.0550, 1.0450, 1.05), # 0.0100
        DummyRow("2023-10-02T00:00:00", 1.04, 1.0600, 1.0500, 1.05), # 0.0100
        DummyRow("2023-10-01T00:00:00", 1.04, 1.0500, 1.0400, 1.05), # 0.0100
    ]
    
    mock_session = AsyncMock()
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
    assert res["room_remaining_pct"] == pytest.approx(0.8) # (1 - 0.0020/0.0100)
    assert res["lookback_days"] == 5

@pytest.mark.asyncio
async def test_compute_daily_range_context_crypto():
    now = datetime.now(timezone.utc)
    today_str = now.isoformat()
    rows = [
        DummyRow(today_str, 29000, 30000, 29500, 29800), # 500
        DummyRow("2023-10-07T00:00:00", 29000, 30100, 29100, 30000), # 1000
        DummyRow("2023-10-06T00:00:00", 29000, 30400, 29400, 30000),
        DummyRow("2023-10-05T00:00:00", 29000, 30200, 29200, 30000),
        DummyRow("2023-10-04T00:00:00", 29000, 29800, 28800, 30000),
        DummyRow("2023-10-03T00:00:00", 29000, 30500, 29500, 30000),
        DummyRow("2023-10-02T00:00:00", 29000, 31000, 30000, 30000),
        DummyRow("2023-10-01T00:00:00", 29000, 30000, 29000, 30000),
    ]
    mock_session = AsyncMock()
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
    mock_session = AsyncMock()
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
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = rows
    mock_session.execute.return_value = mock_result
    
    res = await compute_daily_range_context(mock_session, "EURUSD", {})
    assert res["room_remaining_pct"] == 1.0
