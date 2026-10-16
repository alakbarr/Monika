"""
Tests for MT5 Demo Account detection, PaperGate bypass for demo mode,
and PaperTradeRecord synchronization upon position close.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from monika.application.scheduler.cycle_scheduler import CycleScheduler
from monika.core.analytics.paper_tracker import PaperTracker
from monika.infrastructure.brokers.mt5.client import MT5Client
from monika.infrastructure.database.models import AssetAnalysis, PaperTradeRecord, Position


def test_mt5_client_demo_detection():
    """Verify is_demo_account returns True for trade_mode 0, False for 2."""
    client = MT5Client(settings={})
    assert client.trade_mode is None
    assert client.is_demo_account is False

    client._trade_mode = 0
    assert client.trade_mode == 0
    assert client.is_demo_account is True

    client._trade_mode = 2  # Real
    assert client.trade_mode == 2
    assert client.is_demo_account is False


@pytest.mark.asyncio
async def test_paper_gate_demo_account_allows_auto_execute(monkeypatch):
    """When MT5 is demo account, auto_execute is allowed even if paper trades < 50."""
    settings = {
        "trading": {
            "auto_execute": True,
            "min_paper_trades_before_live": 50,
            "min_paper_win_rate_pct": 55.0,
            "paper_trading": {"enabled": False},
        }
    }
    mock_mt5 = MagicMock()
    mock_mt5.is_demo_account = True
    mock_mt5.account = 12345678

    scheduler = CycleScheduler(settings=settings)
    scheduler._mt5 = mock_mt5

    # Mock PaperTracker statistics to return 3 trades
    mock_tracker = MagicMock()
    mock_tracker.get_statistics = AsyncMock(return_value={"total_trades": 3, "win_rate_pct": 0.0})
    monkeypatch.setattr("monika.core.analytics.paper_tracker.PaperTracker", lambda *args, **kwargs: mock_tracker)

    # Mock session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await scheduler._pre_cycle_setup(mock_session)
    assert result["effective_auto_execute"] is True


@pytest.mark.asyncio
async def test_paper_gate_real_account_suppresses_auto_execute(monkeypatch):
    """When MT5 is real account and paper trades < 50, auto_execute must be suppressed."""
    settings = {
        "trading": {
            "auto_execute": True,
            "min_paper_trades_before_live": 50,
            "min_paper_win_rate_pct": 55.0,
            "paper_trading": {"enabled": False},
        }
    }
    mock_mt5 = MagicMock()
    mock_mt5.is_demo_account = False
    mock_mt5.account = 87654321

    scheduler = CycleScheduler(settings=settings)
    scheduler._mt5 = mock_mt5

    mock_tracker = MagicMock()
    mock_tracker.get_statistics = AsyncMock(return_value={"total_trades": 3, "win_rate_pct": 0.0})
    monkeypatch.setattr("monika.core.analytics.paper_tracker.PaperTracker", lambda *args, **kwargs: mock_tracker)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await scheduler._pre_cycle_setup(mock_session)
    assert result["effective_auto_execute"] is False


@pytest.mark.asyncio
async def test_open_paper_trade_with_kwargs():
    """Verify open_paper_trade uses entry_price and requested_lot from kwargs when no H4 bar is present."""
    tracker = PaperTracker(settings={})
    analysis = MagicMock(spec=AssetAnalysis)
    analysis.id = 42
    analysis.symbol = "EURUSD"
    analysis.action = "buy"
    analysis.stop_loss = 1.0800
    analysis.take_profit = 1.0900
    analysis.entry_condition = json.dumps({"type": "market"})
    analysis.confidence = 0.8
    analysis.holding_period = "intraday"
    analysis.decision_source = "model"
    analysis.was_debate_modified = False

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_res)

    await tracker.open_paper_trade(
        mock_session,
        analysis,
        risk_pct=1.0,
        entry_price=1.0850,
        requested_lot=0.25,
    )

    assert mock_session.add.called
    added = mock_session.add.call_args[0][0]
    assert isinstance(added, PaperTradeRecord)
    assert added.analysis_id == 42
    assert added.symbol == "EURUSD"
    assert added.entry_price == pytest.approx(1.0850, abs=0.001)
    assert added.requested_lot == 0.25


@pytest.mark.asyncio
async def test_sync_positions_from_mt5_syncs_paper_record():
    """Verify sync_positions_from_mt5 marks open PaperTradeRecord as closed with exit price and PnL."""
    client = MT5Client(settings={})
    client.get_open_positions = AsyncMock(return_value=[])
    client.get_orders = AsyncMock(return_value=[])

    mock_deal = MagicMock()
    mock_deal.profit = 150.0
    mock_deal.price = 1.0900
    mock_deal.reason = 4  # tp_hit
    client._run = AsyncMock(return_value=[mock_deal])

    db_pos = MagicMock(spec=Position)
    db_pos.id = 1
    db_pos.is_paper = False
    db_pos.mt5_ticket = 998877
    db_pos.status = "open"
    db_pos.analysis_id = 42
    db_pos.closed_at = None

    pt_record = MagicMock(spec=PaperTradeRecord)
    pt_record.analysis_id = 42
    pt_record.status = "open"
    pt_record.direction = "buy"
    pt_record.entry_price = 1.0850
    pt_record.opened_at = datetime.now(timezone.utc) - timedelta(hours=2)
    pt_record.closed_at = None

    mock_session = AsyncMock()

    def mock_execute(stmt):
        m = MagicMock()
        stmt_str = str(stmt)
        if "positions" in stmt_str:
            m.scalars.return_value.all.return_value = [db_pos]
            m.scalar_one_or_none.return_value = db_pos
        else:
            m.scalar_one_or_none.return_value = pt_record
        return m

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    result = await client.sync_positions_from_mt5(mock_session)
    assert result["closed_in_db"] == 1
    assert db_pos.status == "closed"
    assert pt_record.status == "closed"
    assert pt_record.exit_price == 1.0900
    assert pt_record.exit_reason == "tp_hit"
    assert pt_record.pnl_pct > 0.0
    assert pt_record.holding_hours is not None
