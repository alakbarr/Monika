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


@pytest.mark.asyncio
async def test_point_in_time_dynamic_equity_feedback():
    """Verify that resolving Trade 1 updates self.equity dynamically before sizing Trade 2."""
    from datetime import timedelta
    start = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
    t2_time = start + timedelta(hours=6)
    end = start + timedelta(days=2)

    settings = {}
    engine = PointInTimeBacktestEngine(start, end, settings, mode="replay", initial_equity=10000.0)

    # Analysis 1 at t=0h, Analysis 2 at t=6h
    a1 = AssetAnalysis(
        symbol="EURUSD",
        decision="buy",
        generated_at=start,
        price_at_analysis=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        confidence=0.8,
        confluence_score=5,
        rationale="A1",
    )
    a2 = AssetAnalysis(
        symbol="GBPUSD",
        decision="buy",
        generated_at=t2_time,
        price_at_analysis=1.3000,
        stop_loss=1.2950,
        take_profit=1.3100,
        confidence=0.8,
        confluence_score=5,
        rationale="A2",
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [a1, a2]
    mock_session.execute.return_value = mock_result

    # Evaluator returns: a1 exits at start+2h with +$1,000 (+10%), a2 exits at t2_time+2h with +$500
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate_trade.side_effect = [
        {
            "exit_time": start + timedelta(hours=2),
            "exit_price": 1.1100,
            "exit_reason": "tp_hit",
            "pnl_pips": 100.0,
            "pnl_pct": 10.0,
            "pnl_usd": 1000.0,
        },
        {
            "exit_time": t2_time + timedelta(hours=2),
            "exit_price": 1.3100,
            "exit_reason": "tp_hit",
            "pnl_pips": 100.0,
            "pnl_pct": 5.0,
            "pnl_usd": 550.0,
        },
    ]

    recorded_sizing_equities = []
    original_calc = engine.sizer.calculate_with_session

    async def mock_calc(*args, **kwargs):
        recorded_sizing_equities.append(kwargs.get("account_equity"))
        res = MagicMock()
        res.is_valid = True
        res.recommended_lots = 0.5
        return res

    with patch("backtest.point_in_time_engine.get_session") as mock_get_session, \
         patch("backtest.point_in_time_engine.OutcomeEvaluator", return_value=mock_evaluator), \
         patch.object(engine.sizer, "calculate_with_session", side_effect=mock_calc):

        mock_get_session.return_value.__aenter__.return_value = mock_session
        await engine.run()

    # Verify Trade 1 was sized with initial $10,000
    assert recorded_sizing_equities[0] == 10000.0
    # Verify Trade 2 was sized with compounded $11,000 (after Trade 1 settled)!
    assert recorded_sizing_equities[1] == 11000.0
    # Verify final equity incorporates both
    assert engine.equity == 11550.0

