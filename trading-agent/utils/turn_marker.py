"""
File: utils/turn_marker.py
Durable turn markers for process crash recovery and session auto-continuation.
Persists atomic markers to disk so interrupted analysis cycles or chat turns
can be detected and resumed automatically upon daemon startup.
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.TurnMarker")


@dataclass
class TurnMarker:
    session_id: str
    task_type: str  # recurring_cycle, adhoc_analysis, chat_turn
    symbol: Optional[str]
    stage: str
    started_at: float
    context: Optional[Dict[str, Any]] = None
    attempts: int = 1


class TurnMarkerManager:
    """Manages creation, clearing, and recovery of interrupted execution markers."""

    def __init__(self, marker_dir: Optional[Path] = None):
        if marker_dir:
            self.marker_dir = Path(marker_dir)
        else:
            base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.marker_dir = base_dir / "data" / "markers"
        self.marker_dir.mkdir(parents=True, exist_ok=True)
        self.marker_file = self.marker_dir / "interrupted_turns.json"

    def record_start(self, marker: TurnMarker) -> None:
        """Atomically records start of a critical execution turn."""
        temp_file = self.marker_dir / f"interrupted_{int(time.time()*1000)}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(asdict(marker), f, indent=2)
            os.replace(temp_file, self.marker_file)
            logger.debug(f"Recorded turn start for {marker.task_type} ({marker.symbol or 'all'})")
        except Exception as e:
            logger.warning(f"Failed to record turn marker: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def clear(self) -> None:
        """Clears the marker upon clean task completion."""
        if self.marker_file.exists():
            try:
                self.marker_file.unlink()
                logger.debug("Cleared turn marker successfully.")
            except Exception as e:
                logger.warning(f"Failed to clear turn marker: {e}")

    def check_interrupted(self, max_age_seconds: float = 900.0) -> Optional[TurnMarker]:
        """Checks if an interrupted turn exists and is within the freshness window.
        
        Args:
            max_age_seconds: Maximum age of marker in seconds before considered stale (default: 15 min).
        """
        if not self.marker_file.exists():
            return None

        try:
            with open(self.marker_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            marker = TurnMarker(**data)
            age = time.time() - marker.started_at
            if age > max_age_seconds:
                logger.info(f"Discarding stale interrupted turn marker (age: {age:.1f}s > {max_age_seconds}s)")
                self.clear()
                return None
            if marker.attempts >= 3:
                logger.warning(f"Discarding turn marker after {marker.attempts} failed crash recoveries.")
                self.clear()
                return None
            return marker
        except Exception as e:
            logger.error(f"Error reading turn marker: {e}")
            self.clear()
            return None
