import pytest
from datetime import datetime, timezone, timedelta
from backtest.outcome_evaluator import OutcomeEvaluator
from database.models import BacktestTrade, PriceOHLCV
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_evaluate_buy_tp_hit():
    evaluator = OutcomeEvaluator(max_holding_hours=24)
    trade = BacktestTrade(
        symbol="XAUUSD",
        direction="buy",
        entry_time=datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0
    )
    
    bar = PriceOHLCV(
        timestamp=datetime(2023, 1, 1, 1, 0, tzinfo=timezone.utc),
        low=95.0,
        high=115.0,
        close=110.0
    )
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bar]
    mock_session.execute.return_value = mock_result
    
    with patch("backtest.outcome_evaluator.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        outcome = await evaluator.evaluate_trade(trade)
        
        assert outcome["exit_reason"] == "tp_hit"
        assert outcome["exit_price"] == 110.0
        assert outcome["pnl_pct"] == 10.0

@pytest.mark.asyncio
async def test_evaluate_buy_sl_hit():
    evaluator = OutcomeEvaluator(max_holding_hours=24)
    trade = BacktestTrade(
        symbol="XAUUSD",
        direction="buy",
        entry_time=datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0
    )
    
    bar = PriceOHLCV(
        timestamp=datetime(2023, 1, 1, 1, 0, tzinfo=timezone.utc),
        low=85.0,  # SL hit
        high=115.0, # TP also hit, but SL is checked first (conservative)
        close=90.0
    )
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bar]
    mock_session.execute.return_value = mock_result
    
    with patch("backtest.outcome_evaluator.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        outcome = await evaluator.evaluate_trade(trade)
        
        assert outcome["exit_reason"] == "sl_hit"
        assert outcome["exit_price"] == 90.0
        assert outcome["pnl_pct"] == -10.0
