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
            pnl_pct=-0.8,
            reflection_tags=["sl_too_tight"]
        )

        records = logger.load_recent_trajectories(limit=10)
        assert len(records) == 2
        assert records[0]["symbol"] == "EURUSD"
        assert records[0]["decision"] == "BUY"
        assert records[0]["pnl_pct"] == 1.8
        assert records[1]["symbol"] == "USDJPY"

    finally:
        if os.path.exists(temp_log):
            os.remove(temp_log)
