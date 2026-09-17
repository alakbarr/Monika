import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.strategies.xti_pairs_readiness import XTIPairsReadiness
from analysis.strategies.base_strategy import EdgeSignal


@pytest.mark.asyncio
async def test_xti_pairs_disabled():
    """Verify XTIPairsReadiness returns invalid EdgeSignal when disabled in settings."""
    strategy = XTIPairsReadiness()
    mock_session = AsyncMock()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {
                    "enabled": False
                }
            }
        }
    }

    res = await strategy.evaluate(mock_session, "XTIUSD", settings)
    assert isinstance(res, EdgeSignal)
    assert res.valid is False
    assert "disabled" in res.rationale


@pytest.mark.asyncio
async def test_xti_pairs_missing_data_uses_now_without_error():
    """Verify XTIPairsReadiness executes DB queries using 'now' without NameError."""
    strategy = XTIPairsReadiness()
    mock_session = AsyncMock()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {
                    "enabled": True,
                    "brent_symbol": "XBRUSD"
                }
            }
        }
    }

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
    mock_session = AsyncMock()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {
                    "enabled": True,
                    "brent_symbol": "XBRUSD",
                    "z_entry_threshold": 2.0
                }
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
    mock_session = AsyncMock()
    settings = {
        "trading": {
            "edge_strategy": {
                "xti_pairs_readiness": {
                    "enabled": True,
                    "brent_symbol": "XBRUSD",
                    "z_entry_threshold": 2.0
                }
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

