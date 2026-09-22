"""
Tests for PR-17: Partial Fill & Slippage Tracker.
Verifies slippage calculation, partial fill detection, and Position model persistence.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from database.models import Position, PaperTradeRecord
from execution.service.audit_logger import TradeAuditLogger
from risk.position_sizing import SizingResult


def test_position_model_partial_fill_and_slippage_columns():
    pos = Position(
        symbol="EURUSD",
        direction="buy",
        volume=0.08,
        initial_volume=0.08,
        requested_volume=0.10,
        entry_price=1.0852,
        slippage_pips=0.2,
        partially_filled=True,
    )
    assert pos.symbol == "EURUSD"
    assert pos.volume == 0.08
    assert pos.requested_volume == 0.10
    assert pos.slippage_pips == 0.2
    assert pos.partially_filled is True


def test_paper_trade_record_partial_fill_columns():
    paper = PaperTradeRecord(
        symbol="USDJPY",
        direction="sell",
        entry_price=155.00,
        stop_loss=155.60,
        take_profit=153.80,
        partially_filled=True,
        requested_lot=0.5,
    )
    assert paper.partially_filled is True
    assert paper.requested_lot == 0.5


@pytest.mark.asyncio
async def test_save_position_records_slippage_and_partial_fill():
    mock_session = AsyncMock()

    analysis = MagicMock()
    analysis.id = 123
    analysis.symbol = "EURUSD"
    analysis.decision = "buy"
    analysis.stop_loss = 1.0800
    analysis.take_profit = 1.0900

    sizing = MagicMock(spec=SizingResult)
    sizing.recommended_lots = 0.20
    sizing.entry_price = 1.08500

    # Broker executed only 0.15 lots at 1.08508 (0.8 pips slippage)
    mt5_result = {
        "ticket": 778899,
        "price": 1.08508,
        "volume": 0.15,
    }

    added_objects = []
    mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    pos_id = await TradeAuditLogger.save_position(
        session=mock_session,
        analysis=analysis,
        sizing=sizing,
        mt5_result=mt5_result,
        dry_run=False,
    )

    pos_obj = next(o for o in added_objects if isinstance(o, Position))
    assert pos_obj.volume == 0.15
    assert pos_obj.requested_volume == 0.20
    assert pos_obj.partially_filled is True
    assert pos_obj.entry_price == 1.08508
    assert pos_obj.slippage_pips == 0.8  # (1.08508 - 1.08500) / 0.0001 = 0.8 pips


@pytest.mark.asyncio
async def test_save_position_full_fill_zero_slippage():
    mock_session = AsyncMock()

    analysis = MagicMock()
    analysis.id = 124
    analysis.symbol = "EURUSD"
    analysis.decision = "buy"
    analysis.stop_loss = 1.0800
    analysis.take_profit = 1.0900

    sizing = MagicMock(spec=SizingResult)
    sizing.recommended_lots = 0.10
    sizing.entry_price = 1.08500

    mt5_result = {
        "ticket": 778900,
        "price": 1.08500,
        "volume": 0.10,
    }

    added_objects = []
    mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    await TradeAuditLogger.save_position(
        session=mock_session,
        analysis=analysis,
        sizing=sizing,
        mt5_result=mt5_result,
    )

    pos_obj = next(o for o in added_objects if isinstance(o, Position))
    assert pos_obj.volume == 0.10
    assert pos_obj.requested_volume == 0.10
    assert pos_obj.partially_filled is False
    assert pos_obj.slippage_pips == 0.0
