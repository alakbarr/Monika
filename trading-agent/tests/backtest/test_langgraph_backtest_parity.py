"""
Unit test for LangGraph Parity Mode in PointInTimeBacktestEngine.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from backtest.point_in_time_engine import PointInTimeBacktestEngine
pytest.importorskip("langgraph")
import graph.workflow


@pytest.mark.asyncio
async def test_point_in_time_langgraph_parity_mode():
    """Verify that PointInTimeBacktestEngine executes _run_langgraph_parity_mode when mode='langgraph_parity'."""
    settings = {
        "trading": {
            "asset_universe": ["EURUSD", "XAUUSD"],
            "risk": {
                "account_equity": 10000.0,
                "risk_per_trade_percent": 1.0,
                "max_drawdown_percent": 5.0,
            }
        }
    }

    start = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)

    engine = PointInTimeBacktestEngine(
        start_date=start,
        end_date=end,
        mode="langgraph_parity",
        step_hours=4,
        settings=settings
    )

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "actionable_trades": [
            (
                "EURUSD",
                {
                    "decision": "buy",
                    "entry_price": 1.1000,
                    "stop_loss": 1.0950,
                    "take_profit": 1.1100,
                    "confidence": 85.0,
                    "confluence_score": 8,
                    "rationale": "Bullish order block test"
                }
            )
        ]
    }

    with patch("graph.workflow.build_trading_graph", return_value=mock_graph), \
         patch("backtest.point_in_time_engine.get_session") as mock_get_session, \
         patch("backtest.outcome_evaluator.OutcomeEvaluator.evaluate_trade", new_callable=AsyncMock) as mock_eval:

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_eval.return_value = {
            "exit_time": end,
            "exit_price": 1.1100,
            "exit_reason": "tp_hit",
            "pnl_pips": 100.0,
            "pnl_pct": 1.5,
            "pnl_usd": 150.0
        }

        run_record = await engine.run()

        assert run_record is not None
        assert len(engine.trades) >= 1
        assert engine.trades[0].symbol == "EURUSD"
        assert engine.trades[0].model_used == "langgraph_parity"
        assert mock_graph.ainvoke.called
