import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from backtest.outcome_evaluator import OutcomeEvaluator
from database.models import BacktestTrade, PriceOHLCV

@pytest.mark.asyncio
async def test_session_spread_multiplier():
    evaluator = OutcomeEvaluator()
    
    # 1. Rollover (21:05 UTC) -> 3.5x
    rollover_dt = datetime(2026, 8, 20, 21, 5, tzinfo=timezone.utc)
    assert evaluator._get_session_spread_multiplier(rollover_dt) == 3.5
    
    # 2. Asian session (02:00 UTC) -> 1.8x
    asian_dt = datetime(2026, 8, 20, 2, 0, tzinfo=timezone.utc)
    assert evaluator._get_session_spread_multiplier(asian_dt) == 1.8
    
    # 3. NY/London overlap (14:00 UTC) -> 1.0x
    overlap_dt = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)
    assert evaluator._get_session_spread_multiplier(overlap_dt) == 1.0

@pytest.mark.asyncio
async def test_volatility_slippage():
    evaluator = OutcomeEvaluator()
    
    # Low volatility bar (range = 10 pips)
    bar_low = PriceOHLCV(symbol="EURUSD", timeframe="H1", open=1.1000, high=1.1010, low=1.1000, close=1.1005, volume=100)
    slip_low = evaluator._get_volatility_slippage(bar_low, base_slippage=0.5, pip_size=0.0001)
    assert slip_low == 0.5
    
    # High volatility bar (range = 50 pips)
    bar_high = PriceOHLCV(symbol="EURUSD", timeframe="H1", open=1.1000, high=1.1050, low=1.1000, close=1.1040, volume=500)
    slip_high = evaluator._get_volatility_slippage(bar_high, base_slippage=0.5, pip_size=0.0001)
    assert slip_high > 0.5

@pytest.mark.asyncio
async def test_weekend_gap_slippage():
    evaluator = OutcomeEvaluator()
    
    trade = BacktestTrade(
        symbol="EURUSD",
        direction="buy",
        entry_time=datetime(2026, 8, 21, 20, 0, tzinfo=timezone.utc),
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100
    )
    trade.executed_lots = 1.0
    
    # Sunday open gapped below SL (open at 1.0920 vs SL 1.0950)
    sunday_bar = PriceOHLCV(
        symbol="EURUSD",
        timeframe="H1",
        timestamp=datetime(2026, 8, 23, 21, 0, tzinfo=timezone.utc),
        open=1.0920,
        high=1.0930,
        low=1.0910,
        close=1.0925,
        volume=200
    )
    
    res = evaluator._calculate_outcome(
        trade=trade,
        exit_time=sunday_bar.timestamp,
        exit_price=trade.stop_loss,
        reason="sl_hit",
        bar=sunday_bar,
        apply_costs=True
    )
    
    # Assert filled at gapped open price (1.0920) rather than SL (1.0950)
    assert res["exit_price"] == 1.0920
    assert res["pnl_pips"] < -50.0
