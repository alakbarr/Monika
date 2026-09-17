import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from backtest.point_in_time_engine import PointInTimeBacktestEngine
from database.models import AssetAnalysis

@pytest.mark.asyncio
async def test_replay_mode():
    start = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 1, 2, 0, 0, tzinfo=timezone.utc)
    
    settings = {}
    engine = PointInTimeBacktestEngine(start, end, settings, mode="replay")
    
    # Mock AssetAnalysis
    mock_analysis = AssetAnalysis(
        symbol="XAUUSD",
        decision="buy",
        generated_at=start,
        price_at_analysis=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        confidence=0.8,
        confluence_score=3,
        rationale="Looks good"
    )
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_analysis]
    mock_session.execute.return_value = mock_result
    
    mock_run_record = MagicMock()
    mock_run_record.id = 1
    
    # Mock OutcomeEvaluator
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate_trade.return_value = {
        "exit_time": start,
        "exit_price": 110.0,
        "exit_reason": "tp_hit",
        "pnl_pips": 1000.0,
        "pnl_pct": 10.0
    }
    
    with patch("backtest.point_in_time_engine.get_session") as mock_get_session, \
         patch("backtest.point_in_time_engine.OutcomeEvaluator", return_value=mock_evaluator):
        
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        result = await engine.run()
        
        assert len(engine.trades) == 1
        assert engine.trades[0].pnl_pct == 10.0
        assert engine.equity > 10000.0
        assert result.win_rate == 100.0


@pytest.mark.asyncio
async def test_replay_mode_with_entry_zone_fallback():
    """Verify replay mode extracts entry price from entry_zone when price_at_analysis is None."""
    import json
    start = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 1, 2, 0, 0, tzinfo=timezone.utc)
    
    settings = {}
    engine = PointInTimeBacktestEngine(start, end, settings, mode="replay")
    
    # Mock AssetAnalysis with price_at_analysis=None but valid entry_zone
    mock_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="buy",
        generated_at=start,
        price_at_analysis=None,
        entry_zone=json.dumps({"type": "market", "price": 1.0850}),
        stop_loss=1.0800,
        take_profit=1.0950,
        confidence=0.8,
        confluence_score=5,
        rationale="Edge registry entry"
    )
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_analysis]
    mock_session.execute.return_value = mock_result
    
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate_trade.return_value = {
        "exit_time": start,
        "exit_price": 1.0950,
        "exit_reason": "tp_hit",
        "pnl_pips": 100.0,
        "pnl_pct": 5.0
    }
    
    with patch("backtest.point_in_time_engine.get_session") as mock_get_session, \
         patch("backtest.point_in_time_engine.OutcomeEvaluator", return_value=mock_evaluator):
        
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        result = await engine.run()
        
        assert len(engine.trades) == 1
        assert engine.trades[0].entry_price == 1.0850
        assert engine.trades[0].symbol == "EURUSD"
        assert engine.trades[0].pnl_pct == 5.0
