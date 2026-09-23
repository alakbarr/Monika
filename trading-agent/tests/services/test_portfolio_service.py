# ==============================================================================
# File: tests/services/test_portfolio_service.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock
from services.portfolio_service import PortfolioService
from database.models import Position, Order


@pytest.mark.asyncio
async def test_portfolio_service_get_open_positions():
    mock_session = AsyncMock()
    mock_pos1 = MagicMock(spec=Position, id=1, symbol="EURUSD", status="open", is_paper=True)
    mock_pos2 = MagicMock(spec=Position, id=2, symbol="GBPUSD", status="open", is_paper=False)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_pos1, mock_pos2]
    mock_session.execute.return_value = mock_result

    positions = await PortfolioService.get_open_positions(mock_session, symbol="EURUSD")
    assert len(positions) == 2
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_portfolio_service_metrics_empty():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    metrics = await PortfolioService.get_portfolio_metrics(mock_session)
    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] == 0.0
    assert metrics["total_pnl"] == 0.0


@pytest.mark.asyncio
async def test_portfolio_service_metrics_calculated():
    mock_session = AsyncMock()
    mock_p1 = MagicMock(spec=Position, pnl=100.0, volume=0.1)
    mock_p2 = MagicMock(spec=Position, pnl=-50.0, volume=0.1)
    mock_p3 = MagicMock(spec=Position, pnl=150.0, volume=0.2)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_p1, mock_p2, mock_p3]
    mock_session.execute.return_value = mock_result

    metrics = await PortfolioService.get_portfolio_metrics(mock_session)
    assert metrics["total_trades"] == 3
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1
    assert metrics["win_rate"] == 66.67
    assert metrics["total_pnl"] == 200.0
    assert metrics["profit_factor"] == 5.0
    assert metrics["total_volume"] == 0.4


@pytest.mark.asyncio
async def test_portfolio_service_get_closed_and_orders():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    closed = await PortfolioService.get_closed_positions(mock_session)
    assert closed == []
    orders = await PortfolioService.get_active_orders(mock_session)
    assert orders == []


def test_domain_facades_importable():
    from execution.paper_tracker import PaperTracker
    from agent.chat_agent import ChatAgent
    assert PaperTracker is not None
    assert ChatAgent is not None

