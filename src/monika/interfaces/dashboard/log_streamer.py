# ==============================================================================
# File: logging_observability/dashboard/log_streamer.py
# ==============================================================================

"""
Asynchronous Incremental Log File Tailer & Streamer.
Institutional-grade dashboard observability and transport architecture.

Efficiently tracks and streams incremental log lines from runtime log files
using asynchronous polling with level-based filtering and line buffering.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Dashboard.LogStreamer")

LOG_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def parse_log_line_level(line: str) -> str:
    """Extracts log severity level from standard log line format."""
    for lvl in ["CRITICAL", "ERROR", "WARNING", "WARN", "INFO", "DEBUG"]:
        if f"[{lvl}]" in line or f" {lvl} " in line or f"- {lvl} -" in line:
            return lvl
    return "INFO"


class LogStreamer:
    """Asynchronous file tailer for streaming runtime logs."""

    def __init__(self, log_path: Path, min_level: str = "INFO"):
        self.log_path = log_path
        self.min_level_val = LOG_LEVEL_ORDER.get(min_level.upper(), 20)
        self._last_position: int = 0
        self._stopped: bool = False

    def stop(self) -> None:
        self._stopped = True

    def should_emit(self, line: str) -> bool:
        line_lvl = parse_log_line_level(line)
        line_val = LOG_LEVEL_ORDER.get(line_lvl.upper(), 20)
        return line_val >= self.min_level_val

    async def tail(
        self,
        poll_interval_seconds: float = 0.5,
        max_lines_per_tick: int = 100,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously yields new lines appended to the log file.
        Begins from current end-of-file unless file is smaller than previous position.
        """
        if self.log_path.exists():
            self._last_position = self.log_path.stat().st_size

        while not self._stopped:
            try:
                await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                break
            if not self.log_path.exists():
                continue

            current_size = self.log_path.stat().st_size
            if current_size < self._last_position:
                # File was truncated or rotated
                self._last_position = 0

            if current_size > self._last_position:
                try:
                    with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(self._last_position)
                        lines_read = 0
                        while lines_read < max_lines_per_tick:
                            line = f.readline()
                            if not line:
                                break
                            lines_read += 1
                            if self.should_emit(line):
                                yield line.rstrip("\r\n")
                        self._last_position = f.tell()
                except Exception as e:
                    logger.debug(f"[LogStreamer] Error reading log file: {e}")
