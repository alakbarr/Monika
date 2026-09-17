"""
Unit Tests for PointInTimeBacktestEngine Full Mode Step Execution.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from database.models import PriceOHLCV, BacktestRun, BacktestTrade
from backtest.point_in_time_engine import PointInTimeBacktestEngine
from risk.position_sizing import SizingResult


@pytest.mark.asyncio
async def test_point_in_time_full_mode_step_execution():
    """Verify PointInTimeBacktestEngine steps through time without future lookahead."""
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    settings = {
        "trading": {
            "asset_universe": ["EURUSD"],
            "risk": {"max_risk_amount_usd": 1000.0, "risk_percent_per_trade": 1.0}
        }
    }

    engine = PointInTimeBacktestEngine(
        start_date=start,
        end_date=end,
        settings=settings,
        mode="full",
        step_hours=6,
        initial_equity=10000.0
    )

    # Mock OHLCV bar
    mock_bar = PriceOHLCV(
        symbol="EURUSD",
        timeframe="H1",
        open=1.0800,
        high=1.0850,
        low=1.0780,
        close=1.0820,
        volume=500.0,
        timestamp=start
    )

    mock_session = AsyncMock()
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = mock_bar
    mock_session.execute.return_value = mock_exec_res

    mock_sizing = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.0820,
        stop_loss=1.0780,
        take_profit=1.0900,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0040,
        sl_distance_pips=40.0,
        pip_value_per_lot=10.0,
        raw_lots=0.5,
        recommended_lots=0.5,
        rr_ratio=2.0,
        is_valid=True
    )

    with patch("backtest.point_in_time_engine.get_session") as mock_get_session:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        with patch("analysis.calculators.confluence_calculator.calculate_confluence",
                   AsyncMock(return_value={"buy_potential_score": 8, "sell_potential_score": 4})):
            with patch("analysis.calculators.unified_threshold_calculator.compute_unified_confluence_threshold",
                       AsyncMock(return_value=(7, "base"))):
                with patch("analysis.calculators.regime_classifier.classify_market_regime",
                           AsyncMock(return_value={"regime": "TREND", "volatility_chop": {"chop_block": False}})):
                    with patch("analysis.calculators.daily_range_calculator.compute_daily_range_context",
                               AsyncMock(return_value={"adr": 0.0080})):
                        with patch.object(engine.sizer, "calculate_with_session", AsyncMock(return_value=mock_sizing)):
                            await engine._run_full_mode()

    assert len(engine.trades) >= 1
    assert engine.trades[0].symbol == "EURUSD"
    assert engine.trades[0].direction == "buy"
    assert engine.trades[0].model_used == "point_in_time_pipeline"
    assert engine.trades[0].executed_lots == 0.5
