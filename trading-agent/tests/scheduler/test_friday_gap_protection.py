"""
Unit tests for Friday Market Close Shield and Weekend Gap Risk Protection in PositionGuardian.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from scheduler.position_guardian import PositionGuardian
from database.models import Position
from utils import clock


@pytest.mark.asyncio
async def test_friday_close_protection_triggers_auto_close():
    """Verify that PositionGuardian closes non-exempt positions on Friday 20:30 UTC when auto_close is True."""
    settings = {
        "trading": {
            "weekend_management": {
                "strategy": "close_positions",
                "auto_close_friday_positions": True,
                "exempted_symbols": ["BTCUSD"]
            }
        }
    }

    mock_exec_service = AsyncMock()
    guardian = PositionGuardian(settings=settings, execution_service=mock_exec_service)

    # Friday at 20:30 UTC
    friday_time = datetime(2026, 8, 28, 20, 30, tzinfo=timezone.utc)
    assert friday_time.weekday() == 4  # Friday

    mock_pos_eur = Position(id=1, symbol="EURUSD", status="open", mt5_ticket=1001, volume=0.5, entry_price=1.10)
    mock_pos_btc = Position(id=2, symbol="BTCUSD", status="open", mt5_ticket=1002, volume=0.1, entry_price=60000)

    with clock.frozen_time(friday_time), \
         patch("scheduler.position_guardian.get_session") as mock_get_session, \
         patch("utils.infra.notifier.AgentNotifier.send_info", new_callable=AsyncMock) as mock_notify:

        mock_session = AsyncMock()
        mock_exec = MagicMock()
        mock_exec.scalars.return_value.all.return_value = [mock_pos_eur, mock_pos_btc]
        mock_session.execute.return_value = mock_exec
        mock_get_session.return_value.__aenter__.return_value = mock_session

        res = await guardian.check_friday_close_protection()

        assert res.get("auto_closed") == 1
        assert mock_exec_service.close_position_by_ticket.called
        # Verify EURUSD closed, but BTCUSD exempted
        call_args = mock_exec_service.close_position_by_ticket.call_args[0]
        assert call_args[0] == 1001


@pytest.mark.asyncio
async def test_friday_close_protection_skips_on_non_friday():
    """Verify that PositionGuardian skips check when current time is not Friday 20:00-21:30 UTC."""
    settings = {"trading": {"weekend_management": {"strategy": "close_positions"}}}
    guardian = PositionGuardian(settings=settings)

    # Thursday 20:30 UTC
    thursday_time = datetime(2026, 8, 27, 20, 30, tzinfo=timezone.utc)
    with clock.frozen_time(thursday_time):
        res = await guardian.check_friday_close_protection()
        assert res.get("skipped") is True
