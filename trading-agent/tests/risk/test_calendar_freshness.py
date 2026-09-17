# ==============================================================================
# File: tests/risk/test_calendar_freshness.py
# ==============================================================================
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

from risk.risk_gate import RiskGate


@pytest.fixture
def settings():
    return {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 3.0,
                "max_concurrent_positions": 5,
                "max_lot_size": 1.0,
                "correlation_limit": 3,
                "news_window_minutes": 15,
                "max_portfolio_heat_pct": 4.0
            }
        }
    }


@pytest.mark.asyncio
async def test_calendar_fresh_under_4h(settings):
    """Calendar data is fresh (< 4h) -> approved without warnings."""
    gate = RiskGate(settings)
    mock_session = AsyncMock()

    now = datetime.now(timezone.utc)
    mock_cfg = MagicMock()
    mock_cfg.value = (now - timedelta(hours=2)).isoformat()

    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = mock_cfg

    mock_res_count = MagicMock()
    mock_res_count.scalar_one_or_none.return_value = 100

    mock_res_future = MagicMock()
    mock_res_future.scalar_one_or_none.return_value = 1

    mock_res_upcoming = MagicMock()
    mock_res_upcoming.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_res_cfg, mock_res_count, mock_res_future, mock_res_upcoming]

    ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
    assert ok
    assert "WARNING" not in reason


@pytest.mark.asyncio
async def test_calendar_age_between_4_and_8h(settings):
    """Calendar data between 4h and 8h -> approved with warning."""
    gate = RiskGate(settings)
    mock_session = AsyncMock()

    now = datetime.now(timezone.utc)
    mock_cfg = MagicMock()
    mock_cfg.value = (now - timedelta(hours=5)).isoformat()

    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = mock_cfg

    mock_res_count = MagicMock()
    mock_res_count.scalar_one_or_none.return_value = 100

    mock_res_future = MagicMock()
    mock_res_future.scalar_one_or_none.return_value = 1

    mock_res_upcoming = MagicMock()
    mock_res_upcoming.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_res_cfg, mock_res_count, mock_res_future, mock_res_upcoming]

    ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
    assert ok
    assert "WARNING" in reason
    assert "5.0h old" in reason


@pytest.mark.asyncio
async def test_calendar_age_over_8h_with_future_coverage(settings):
    """Calendar fetch > 8h (e.g. 11.1h) but future schedule exists in DB -> approved with soft warning."""
    gate = RiskGate(settings)
    mock_session = AsyncMock()

    now = datetime.now(timezone.utc)
    mock_cfg = MagicMock()
    mock_cfg.value = (now - timedelta(hours=11.1)).isoformat()

    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = mock_cfg

    mock_res_count = MagicMock()
    mock_res_count.scalar_one_or_none.return_value = 100

    # Future coverage is found in DB
    mock_res_future = MagicMock()
    mock_res_future.scalar_one_or_none.return_value = 42

    mock_res_upcoming = MagicMock()
    mock_res_upcoming.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_res_cfg, mock_res_count, mock_res_future, mock_res_upcoming]

    ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
    assert ok
    assert "WARNING" in reason
    assert "degraded mode" in reason


@pytest.mark.asyncio
async def test_calendar_age_over_8h_without_future_coverage(settings):
    """Calendar fetch > 8h in degraded mode -> allowed with warning if no high-impact upcoming."""
    gate = RiskGate(settings)
    mock_session = AsyncMock()

    now = datetime.now(timezone.utc)
    mock_cfg = MagicMock()
    mock_cfg.value = (now - timedelta(hours=11.1)).isoformat()

    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = mock_cfg

    mock_res_count = MagicMock()
    mock_res_count.scalar_one_or_none.return_value = 100

    # No future coverage
    mock_res_future = MagicMock()
    mock_res_future.scalar_one_or_none.return_value = None

    mock_res_upcoming = MagicMock()
    mock_res_upcoming.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_res_cfg, mock_res_count, mock_res_future, mock_res_upcoming]

    ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
    assert ok
    assert "degraded mode" in reason


@pytest.mark.asyncio
async def test_calendar_empty_database(settings):
    """No calendar rows in DB -> degraded mode pass with warning."""
    gate = RiskGate(settings)
    mock_session = AsyncMock()

    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = None

    mock_res_max = MagicMock()
    mock_res_max.scalar_one_or_none.return_value = None

    mock_res_count = MagicMock()
    mock_res_count.scalar_one_or_none.return_value = 0

    mock_session.execute.side_effect = [mock_res_cfg, mock_res_max, mock_res_count]

    ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
    assert ok
    assert "economic_calendar_empty_warning_pass" in reason
