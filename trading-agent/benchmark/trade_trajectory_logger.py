"""
Trade Trajectory Logger — Decision Tracing for GEPA Prompt Evolution.

Logs the full lifecycle trace of trade decisions (from Stage 1 Macro to MT5 fill & PnL outcome)
in structured JSONL format for offline reflective prompt optimization.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger("TradingAgent.TradeTrajectoryLogger")


class TradeTrajectoryLogger:
    """Records trade trajectories into persistent JSONL logs for GEPA evolutionary learning."""

    def __init__(self, log_path: Optional[str] = None):
        if log_path:
            self.log_path = Path(log_path)
        else:
            base_dir = Path(__file__).resolve().parent.parent / "logs"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = base_dir / "trade_trajectories.jsonl"

    def log_trajectory(
        self,
        symbol: str,
        decision: str,
        fundamental_brief: Optional[Dict[str, Any]] = None,
        specialist_outputs: Optional[Dict[str, Any]] = None,
        debate_verdict: Optional[Dict[str, Any]] = None,
        risk_decision: Optional[Dict[str, Any]] = None,
        execution_details: Optional[Dict[str, Any]] = None,
        pnl_pct: Optional[float] = None,
        mae_points: Optional[float] = None,
        mfe_points: Optional[float] = None,
        reflection_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Appends a complete trade decision record to the JSONL log file."""
        record: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "decision": decision.upper(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fundamental_brief": fundamental_brief or {},
            "specialist_outputs": specialist_outputs or {},
            "debate_verdict": debate_verdict or {},
            "risk_decision": risk_decision or {},
            "execution_details": execution_details or {},
            "pnl_pct": pnl_pct,
            "mae_points": mae_points,
            "mfe_points": mfe_points,
            "reflection_tags": reflection_tags or [],
        }

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to log trade trajectory for {symbol}: {e}")

        return record

    def load_recent_trajectories(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Loads most recent N trade trajectories for reflection."""
        if not self.log_path.exists():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading trade trajectories: {e}")

        return records[-limit:]
