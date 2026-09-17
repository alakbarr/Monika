import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from analysis.stages.preflight_gate import PreFlightTurnGate, EMPIRICAL_ACTIVE_MEDIANS

@pytest.mark.asyncio
async def test_preflight_active_hours_normal_spread():
    # Active hour: 14:30 UTC
    test_time = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    mock_mt5 = MagicMock()
    mock_tick = MagicMock()
    mock_tick.time = test_time.timestamp()
    mock_tick.spread = 9.0  # EURUSD median is 8.0, 9.0 is 1.12x (normal)
    mock_mt5.get_latest_tick = AsyncMock(return_value=mock_tick)

    is_allowed, reason = await PreFlightTurnGate.evaluate_preconditions(
        session=None,
        symbol="EURUSD",
        settings={"trading": {"24_7_assets": ["BTCUSD"]}},
        mt5_client=mock_mt5,
        override_time=test_time,
    )
    assert is_allowed is True
    assert reason is None

@pytest.mark.asyncio
async def test_preflight_active_hours_abnormal_spread():
    # Active hour: 14:30 UTC
    test_time = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    mock_mt5 = MagicMock()
    mock_tick = MagicMock()
    mock_tick.time = test_time.timestamp()
    mock_tick.spread = 22.0  # EURUSD median is 8.0, 22.0 > 2.0x (16.0) -> abnormal
    mock_mt5.get_latest_tick = AsyncMock(return_value=mock_tick)

    is_allowed, reason = await PreFlightTurnGate.evaluate_preconditions(
        session=None,
        symbol="EURUSD",
        settings={},
        mt5_client=mock_mt5,
        override_time=test_time,
    )
    assert is_allowed is False
    assert "Abnormal active spread expansion" in reason

@pytest.mark.asyncio
async def test_preflight_rollover_window_blocks_fx():
    # Rollover window: 21:58 UTC
    test_time = datetime(2026, 9, 4, 21, 58, tzinfo=timezone.utc)
    is_allowed, reason = await PreFlightTurnGate.evaluate_preconditions(
        session=None,
        symbol="EURUSD",
        settings={},
        override_time=test_time,
    )
    assert is_allowed is False
    assert "Rollover/Off-peak liquidity window" in reason

@pytest.mark.asyncio
async def test_preflight_rollover_window_allows_crypto():
    # Rollover window: 21:58 UTC, but BTCUSD is 24/7
    test_time = datetime(2026, 9, 4, 21, 58, tzinfo=timezone.utc)
    mock_mt5 = MagicMock()
    mock_tick = MagicMock()
    mock_tick.time = test_time.timestamp()
    mock_tick.spread = 1965.0  # BTCUSD normal
    mock_mt5.get_latest_tick = AsyncMock(return_value=mock_tick)

    is_allowed, reason = await PreFlightTurnGate.evaluate_preconditions(
        session=None,
        symbol="BTCUSD",
        settings={"trading": {"24_7_assets": ["BTCUSD"]}},
        mt5_client=mock_mt5,
        override_time=test_time,
    )
    assert is_allowed is True
    assert reason is None

@pytest.mark.asyncio
async def test_preflight_stale_quote_blocks_turn():
    # Active hour, but tick is 120s old
    test_time = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    mock_mt5 = MagicMock()
    mock_tick = MagicMock()
    mock_tick.time = test_time.timestamp() - 120  # 120s old
    mock_tick.spread = 8.0
    mock_mt5.get_latest_tick = AsyncMock(return_value=mock_tick)

    is_allowed, reason = await PreFlightTurnGate.evaluate_preconditions(
        session=None,
        symbol="EURUSD",
        settings={},
        mt5_client=mock_mt5,
        override_time=test_time,
    )
    assert is_allowed is False
    assert "MT5 quote stale" in reason

@pytest.mark.asyncio
async def test_preflight_high_impact_news_freeze():
    # Active hour, spread normal, but near news
    test_time = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    mock_mt5 = MagicMock()
    mock_tick = MagicMock()
    mock_tick.time = test_time.timestamp()
    mock_tick.spread = 8.0
    mock_mt5.get_latest_tick = AsyncMock(return_value=mock_tick)
    mock_session = AsyncMock()

    with patch.object(PreFlightTurnGate, "check_high_impact_news", AsyncMock(return_value=(True, "US Non-Farm Payrolls (USD)"))):
        is_allowed, reason = await PreFlightTurnGate.evaluate_preconditions(
            session=mock_session,
            symbol="EURUSD",
            settings={},
            mt5_client=mock_mt5,
            override_time=test_time,
        )
        assert is_allowed is False
        assert "US Non-Farm Payrolls" in reason
