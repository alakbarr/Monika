# ==============================================================================
# File: tests/services/test_trading_service.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.services.portfolio_service import PortfolioService
from monika.application.services.trading_service import TradingService
from monika.domain.entities.position import PositionEntity
from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_trading_service_modify_position_success():
    mock_session = create_mock_async_session()
    mock_pos = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.0900,
        tp=1.1200,
        status="open",
        mt5_ticket=1001,
        is_paper=True,
    )

    # Mock position repository in TradingService
    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_by_ticket = AsyncMock(return_value=mock_pos)
        mock_repo.update_sl_tp = AsyncMock(return_value=mock_pos)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        ok = await TradingService.modify_position(
            session=mock_session,
            ticket=1001,
            sl=1.0950,
            tp=1.1250,
            actor="test_runner",
        )
        assert ok is True
        mock_repo.get_by_ticket.assert_awaited_once_with(1001, open_only=True)
        mock_repo.update_sl_tp.assert_awaited_once_with(ticket=1001, sl=1.0950, tp=1.1250)


@pytest.mark.asyncio
async def test_trading_service_close_positions_batch():
    mock_session = create_mock_async_session()
    mock_pos1 = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        status="open",
        mt5_ticket=1001,
        is_paper=True,
    )
    mock_pos2 = PositionEntity(
        id=2,
        symbol="GBPUSD",
        direction="sell",
        volume=0.2,
        entry_price=1.2500,
        status="open",
        mt5_ticket=1002,
        is_paper=True,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()

        async def _mock_get(ticket, open_only=True):
            if ticket == 1001:
                return mock_pos1
            if ticket == 1002:
                return mock_pos2
            return None

        mock_repo.get_by_ticket = AsyncMock(side_effect=_mock_get)
        mock_repo.close_position = AsyncMock(return_value=mock_pos1)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        res = await TradingService.close_positions_batch(
            session=mock_session,
            tickets=[1001, 1002, 9999],
            reason="Test batch close",
            actor="test_runner",
        )
        assert res["success"] is True
        assert res["closed_count"] == 2
        assert res["failed_count"] == 1
        assert res["tickets"] == [1001, 1002, 9999]


@pytest.mark.asyncio
async def test_trading_service_bulk_breakeven():
    mock_session = create_mock_async_session()

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.apply_bulk_breakeven = AsyncMock(return_value=3)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        res = await TradingService.bulk_breakeven(
            session=mock_session,
            symbol="EURUSD",
            actor="test_runner",
        )
        assert res["success"] is True
        assert res["updated_count"] == 3
        mock_repo.apply_bulk_breakeven.assert_awaited_once_with(symbol="EURUSD")


@pytest.mark.asyncio
async def test_trading_service_set_trailing_override():
    mock_session = create_mock_async_session()
    mock_pos = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        status="open",
        mt5_ticket=1001,
        is_paper=True,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_by_ticket = AsyncMock(return_value=mock_pos)
        mock_repo.update_trailing_override = AsyncMock(return_value=mock_pos)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        updated = await TradingService.set_trailing_override(
            session=mock_session,
            ticket=1001,
            override_data={"trailing_pips": 15.0},
            actor="test_runner",
        )
        assert updated is not None
        mock_repo.update_trailing_override.assert_awaited_once()


@pytest.mark.asyncio
async def test_portfolio_service_get_order_logs():
    mock_session = create_mock_async_session()
    mock_log = MagicMock(id=1, action="place", symbol="EURUSD")

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_recent_order_logs = AsyncMock(return_value=[mock_log])
        mp.setattr(
            "monika.application.services.portfolio_service.PositionRepository",
            lambda s: mock_repo,
        )

        logs = await PortfolioService.get_order_logs(mock_session, limit=10, action="place")
        assert len(logs) == 1
        assert logs[0].action == "place"
        mock_repo.get_recent_order_logs.assert_awaited_once_with(limit=10, action="place")
