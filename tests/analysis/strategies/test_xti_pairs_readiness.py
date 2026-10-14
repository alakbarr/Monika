from tests.conftest import create_mock_async_session
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from monika.application.analysis.strategies.xti_pairs_readiness import XTIPairsReadiness
from monika.application.analysis.strategies.base_strategy import EdgeSignal


@pytest.mark.asyncio
async def test_xti_pairs_disabled():
    """Verify XTIPairsReadiness returns invalid EdgeSignal when disabled in settings."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {"trading": {"edge_strategy": {"xti_pairs_readiness": {"enabled": False}}}}

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert isinstance(res, EdgeSignal)
    assert res.valid is False
    assert "disabled" in res.rationale


@pytest.mark.asyncio
async def test_xti_pairs_missing_data_uses_now_without_error():
    """Verify XTIPairsReadiness executes DB queries using 'now' without NameError."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {"trading": {"edge_strategy": {"xti_pairs_readiness": {"enabled": True, "brent_symbol": "XBRUSD"}}}}

    # Mock DB execution returning empty list
    mock_res = MagicMock()
    mock_res.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_res)

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert isinstance(res, EdgeSignal)
    assert res.valid is False
    assert "XBRUSD data missing" in res.rationale


@pytest.mark.asyncio
async def test_xti_pairs_successful_buy_signal_and_hedge_leg():
    """Verify XTIPairsReadiness generates dual-leg stat-arb buy signal when spread is abnormally wide."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {"enabled": True, "brent_symbol": "XBRUSD", "z_entry_threshold": 2.0}
            }
        }
    }

    base_time = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    # Generate 15 days of data
    # Historical spread around 5.0 with slight variance (std > 0)
    # Latest day spread = 15.0 (Brent 85, WTI 70) -> spread abnormally wide (Z > 2.0) -> BUY WTI, SELL Brent
    brent_data = []
    xti_data = []
    for i in range(14):
        dt = base_time + timedelta(days=i)
        brent_data.append((dt, 80.0 + (i * 0.2)))
        # Slight variation in spread: 4.8, 5.0, 5.2
        xti_offset = 75.0 + (i * 0.2) + ((i % 3 - 1) * 0.2)
        xti_data.append((dt, xti_offset))

    # Latest day (extreme spread)
    dt_latest = base_time + timedelta(days=14)
    brent_data.append((dt_latest, 85.0))
    xti_data.append((dt_latest, 70.0))

    # Reverse order like order_by desc
    brent_rows = list(reversed(brent_data))
    xti_rows = list(reversed(xti_data))

    brent_res = MagicMock()
    brent_res.all.return_value = brent_rows

    xti_res = MagicMock()
    xti_res.all.return_value = xti_rows

    # Call 1: Brent, Call 2: XTI
    mock_session.execute = AsyncMock(side_effect=[brent_res, xti_res])

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert isinstance(res, EdgeSignal)
    assert res.valid is True
    assert res.direction == "buy"
    assert res.symbol == "XTIUSD"
    assert "WTI is undervalued" in res.rationale

    # Verify hedge leg
    assert res.paired_leg is not None
    assert isinstance(res.paired_leg, EdgeSignal)
    assert res.paired_leg.symbol == "XBRUSD"
    assert res.paired_leg.direction == "sell"
    assert res.paired_leg.valid is True


@pytest.mark.asyncio
async def test_xti_pairs_successful_sell_signal_and_hedge_leg():
    """Verify XTIPairsReadiness generates sell signal when spread is abnormally tight (Z < -2.0)."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {"enabled": True, "brent_symbol": "XBRUSD", "z_entry_threshold": 2.0}
            }
        }
    }

    base_time = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    brent_data = []
    xti_data = []
    for i in range(14):
        dt = base_time + timedelta(days=i)
        brent_data.append((dt, 80.0 + (i * 0.2)))
        xti_offset = 75.0 + (i * 0.2) + ((i % 3 - 1) * 0.2)
        xti_data.append((dt, xti_offset))

    # Latest day (abnormally tight spread, e.g. -5.0 -> WTI overvalued)
    dt_latest = base_time + timedelta(days=14)
    brent_data.append((dt_latest, 75.0))
    xti_data.append((dt_latest, 85.0))

    brent_rows = list(reversed(brent_data))
    xti_rows = list(reversed(xti_data))

    brent_res = MagicMock()
    brent_res.all.return_value = brent_rows
    xti_res = MagicMock()
    xti_res.all.return_value = xti_rows

    mock_session.execute = AsyncMock(side_effect=[brent_res, xti_res])

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert isinstance(res, EdgeSignal)
    assert res.valid is True
    assert res.direction == "sell"
    assert res.symbol == "XTIUSD"
    assert "WTI is overvalued" in res.rationale

    # Verify hedge leg (should buy Brent)
    assert res.paired_leg is not None
    assert isinstance(res.paired_leg, EdgeSignal)
    assert res.paired_leg.symbol == "XBRUSD"
    assert res.paired_leg.direction == "buy"
    assert res.paired_leg.valid is True


def test_xti_pairs_regimes_excludes_trend():
    """Verify XTIPairsReadiness does not include TREND in compatible_regimes."""
    assert "TREND" not in XTIPairsReadiness.compatible_regimes
    assert "RANGE" in XTIPairsReadiness.compatible_regimes


@pytest.mark.asyncio
async def test_xti_pairs_rejects_non_stationary_trending_spread():
    """Verify XTIPairsReadiness rejects signal when spread is non-stationary / trending (ADF p > 0.15)."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {
                    "enabled": True,
                    "brent_symbol": "XBRUSD",
                    "z_entry_threshold": 2.0,
                    "adf_max_pvalue": 0.15,
                }
            }
        }
    }

    base_time = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    # Generate 25 days of monotonically drifting / trending spread (random walk with drift: non-stationary)
    brent_data = []
    xti_data = []
    for i in range(25):
        dt = base_time + timedelta(days=i)
        # Brent drifts upward strongly while XTI stays flat -> spread strongly trending
        brent_data.append((dt, 70.0 + (i * 0.8)))
        xti_data.append((dt, 70.0))

    # Latest bar triggers high Z-score
    dt_latest = base_time + timedelta(days=25)
    brent_data.append((dt_latest, 100.0))
    xti_data.append((dt_latest, 70.0))

    brent_res = MagicMock()
    brent_res.all.return_value = list(reversed(brent_data))
    xti_res = MagicMock()
    xti_res.all.return_value = list(reversed(xti_data))
    mock_session.execute = AsyncMock(side_effect=[brent_res, xti_res])

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert isinstance(res, EdgeSignal)
    assert res.valid is False
    assert "REJECTED: Spread non-stationary" in res.rationale


@pytest.mark.asyncio
async def test_xti_pairs_dollar_neutral_size_multiplier():
    """Verify hedge leg has correct dollar-neutral size_multiplier = last_xti / brent."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {"enabled": True, "brent_symbol": "XBRUSD", "z_entry_threshold": 2.0}
            }
        }
    }

    base_time = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    brent_data = []
    xti_data = []
    for i in range(14):
        dt = base_time + timedelta(days=i)
        brent_data.append((dt, 100.0 + (i * 0.1)))
        xti_offset = 80.0 + (i * 0.1) + ((i % 3 - 1) * 0.2)
        xti_data.append((dt, xti_offset))

    # Latest: Brent = 110.0, XTI = 80.0 -> spread 30.0 -> Z > 2.0
    dt_latest = base_time + timedelta(days=14)
    brent_data.append((dt_latest, 110.0))
    xti_data.append((dt_latest, 80.0))

    brent_res = MagicMock()
    brent_res.all.return_value = list(reversed(brent_data))
    xti_res = MagicMock()
    xti_res.all.return_value = list(reversed(xti_data))
    mock_session.execute = AsyncMock(side_effect=[brent_res, xti_res])

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert res.valid is True
    assert res.paired_leg is not None
    # 80.0 / 110.0 = 0.73
    assert res.paired_leg.meta.get("size_multiplier") == 0.73
    assert res.meta.get("hedge_ratio") == 0.73


@pytest.mark.asyncio
async def test_xti_pairs_rejects_zero_or_negative_price():
    """Verify XTIPairsReadiness fails closed if prices are zero or negative."""
    strategy = XTIPairsReadiness()
    mock_session = create_mock_async_session()
    settings = {"trading": {"edge_strategy": {"xti_pairs_readiness": {"enabled": True, "brent_symbol": "XBRUSD"}}}}

    dt = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    brent_res = MagicMock()
    brent_res.all.return_value = [(dt, 0.0)]
    xti_res = MagicMock()
    xti_res.all.return_value = [(dt, 70.0)]
    mock_session.execute = AsyncMock(side_effect=[brent_res, xti_res])

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert res.valid is False
