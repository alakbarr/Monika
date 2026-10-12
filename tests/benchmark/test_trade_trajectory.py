import pytest
import tempfile
import os
import json
from benchmark.trade_trajectory_logger import TradeTrajectoryLogger


def test_trade_trajectory_logger():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        temp_log = tf.name

    try:
        logger = TradeTrajectoryLogger(log_path=temp_log)
        
        # Log 2 sample trajectories
        logger.log_trajectory(
            symbol="EURUSD",
            decision="BUY",
            ticket=123456,
            fundamental_brief={"bias": "bullish"},
            specialist_outputs={"technical": {"bias": "BULLISH"}},
            debate_verdict={"decision": "buy", "risk_multiplier": 0.8},
            risk_decision={"approved": True, "lot_size": 0.5},
            pnl_pct=1.8,
            mae_points=12.0,
            mfe_points=35.0,
            reflection_tags=["good_process_good_outcome"]
        )
        logger.log_trajectory(
            symbol="USDJPY",
            decision="SELL",
            ticket=654321,
            pnl_pct=-0.8,
            reflection_tags=["sl_too_tight"]
        )

        records = logger.load_recent_trajectories(limit=10)
        assert len(records) == 2
        assert records[0]["symbol"] == "EURUSD"
        assert records[0]["decision"] == "BUY"
        assert records[0]["ticket"] == 123456
        assert records[0]["pnl_pct"] == 1.8
        assert records[1]["symbol"] == "USDJPY"
        assert records[1]["ticket"] == 654321

        # Test updating trajectory outcome by ticket
        ok = logger.update_trajectory_outcome(
            ticket=123456,
            pnl_pct=2.5,
            pnl_usd=250.0,
            reflection_tags=["tp_hit", "runner_maximized"]
        )
        assert ok is True

        updated_records = logger.load_recent_trajectories(limit=10)
        assert updated_records[0]["pnl_pct"] == 2.5
        assert updated_records[0]["pnl_usd"] == 250.0
        assert "tp_hit" in updated_records[0]["reflection_tags"]
        assert "good_process_good_outcome" in updated_records[0]["reflection_tags"]

        # Test updating trajectory outcome by symbol fallback
        ok_sym = logger.update_trajectory_outcome(
            symbol="USDJPY",
            pnl_pct=-1.2,
            pnl_usd=-120.0,
            reflection_tags=["sl_hit"]
        )
        assert ok_sym is True
        updated_records2 = logger.load_recent_trajectories(limit=10)
        assert updated_records2[1]["pnl_pct"] == -1.2
        assert updated_records2[1]["pnl_usd"] == -120.0
        assert "sl_hit" in updated_records2[1]["reflection_tags"]

    finally:
        if os.path.exists(temp_log):
            os.remove(temp_log)
