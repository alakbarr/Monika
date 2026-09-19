"""
Trade Trajectory Logger — Decision Tracing for GEPA Prompt Evolution.

Logs the full lifecycle trace of trade decisions (from Stage 1 Macro to MT5 fill & PnL outcome)
in structured JSONL format for offline reflective prompt optimization.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from contextlib import contextmanager

logger = logging.getLogger("TradingAgent.TradeTrajectoryLogger")


@contextmanager
def file_lock(f):
    """Cross-platform advisory file locking (Windows msvcrt / POSIX fcntl)."""
    try:
        if sys.platform == "win32":
            import msvcrt
            pos = f.tell()
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            f.seek(pos)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    except Exception as e:
        logger.debug(f"File locking failed/ignored: {e}")
    try:
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt
                pos = f.tell()
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                f.seek(pos)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass


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
        ticket: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Appends a complete trade decision record to the JSONL log file with atomic lock."""
        record: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "decision": decision.upper(),
            "ticket": ticket,
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
                with file_lock(f):
                    f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to log trade trajectory for {symbol}: {e}")

        return record

    def update_trajectory_outcome(
        self,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
        pnl_pct: Optional[float] = None,
        pnl_usd: Optional[float] = None,
        mae_points: Optional[float] = None,
        mfe_points: Optional[float] = None,
        reflection_tags: Optional[List[str]] = None,
    ) -> bool:
        """Updates trade outcome metrics (PnL, MAE, MFE) for an existing trajectory upon closure."""
        if not self.log_path.exists():
            return False

        try:
            with open(self.log_path, "r+", encoding="utf-8") as f:
                with file_lock(f):
                    lines = f.readlines()
                    target_idx = None
                    for i in range(len(lines) - 1, -1, -1):
                        line_str = lines[i].strip()
                        if not line_str:
                            continue
                        try:
                            rec = json.loads(line_str)
                            if ticket is not None and rec.get("ticket") == ticket:
                                target_idx = i
                                break
                            elif ticket is None and symbol and rec.get("symbol") == symbol.upper():
                                target_idx = i
                                break
                        except Exception:
                            continue

                    if target_idx is not None:
                        rec = json.loads(lines[target_idx].strip())
                        if pnl_pct is not None:
                            rec["pnl_pct"] = pnl_pct
                        if pnl_usd is not None:
                            rec["pnl_usd"] = pnl_usd
                        if mae_points is not None:
                            rec["mae_points"] = mae_points
                        if mfe_points is not None:
                            rec["mfe_points"] = mfe_points
                        if reflection_tags:
                            current_tags = rec.get("reflection_tags") or []
                            for tag in reflection_tags:
                                if tag not in current_tags:
                                    current_tags.append(tag)
                            rec["reflection_tags"] = current_tags

                        lines[target_idx] = json.dumps(rec) + "\n"
                        f.seek(0)
                        f.writelines(lines)
                        f.truncate()
                        return True

            return False
        except Exception as e:
            logger.error(f"Failed to update trajectory outcome (ticket={ticket}, symbol={symbol}): {e}")
            return False

    def load_recent_trajectories(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Loads most recent N trade trajectories for reflection."""
        if not self.log_path.exists():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                with file_lock(f):
                    for line in f:
                        line = line.strip()
                        if line:
                            records.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading trade trajectories: {e}")

        return records[-limit:]
