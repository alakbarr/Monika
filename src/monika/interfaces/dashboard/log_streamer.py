# ==============================================================================
# File: logging_observability/dashboard/log_streamer.py
# ==============================================================================

"""
Asynchronous Incremental Log File Tailer and Streamer.
Institutional-grade dashboard observability and transport architecture.

Efficiently tracks and streams incremental log lines from runtime log files
using asynchronous polling with level-based filtering, line buffering, and secret redaction.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator, List, Tuple

from monika.core.security.log_redactor import redact_sensitive_text

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
    """Asynchronous file tailer for streaming runtime logs with secret redaction."""

    def __init__(self, log_path: Path, min_level: str = "INFO"):
        self.log_path = log_path
        self.min_level_val = LOG_LEVEL_ORDER.get(min_level.upper(), 20)
        self._last_position: int = 0
        self._stopped: bool = False

        # Guard against arbitrary path traversal outside logs or non-log extensions
        try:
            resolved = self.log_path.resolve()
            allowed_base = Path("logs").resolve()
            if not (resolved.is_relative_to(allowed_base) or resolved.suffix in (".log", ".jsonl", ".txt")):
                logger.warning(f"[LogStreamer] Non-standard log path: {self.log_path}")
        except Exception as e:
            logger.debug(f"[LogStreamer] Path resolution warning: {e}")

    def stop(self) -> None:
        self._stopped = True

    def should_emit(self, line: str) -> bool:
        line_lvl = parse_log_line_level(line)
        line_val = LOG_LEVEL_ORDER.get(line_lvl.upper(), 20)
        return line_val >= self.min_level_val

    def _read_chunk(self, position: int, max_lines: int) -> Tuple[List[str], int]:
        """Synchronous disk reading and redaction offloaded to worker thread."""
        if not self.log_path.exists():
            return [], position

        try:
            current_size = self.log_path.stat().st_size
        except Exception:
            return [], position

        if current_size < position:
            position = 0

        lines: List[str] = []
        new_pos = position

        if current_size > position:
            try:
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(position)
                    while len(lines) < max_lines:
                        line = f.readline()
                        if not line:
                            break
                        if self.should_emit(line):
                            sanitized = redact_sensitive_text(line.rstrip("\r\n"))
                            lines.append(sanitized)
                    new_pos = f.tell()
            except Exception as e:
                logger.debug(f"[LogStreamer] Error reading log file: {e}")

        return lines, new_pos

    async def tail(
        self,
        poll_interval_seconds: float = 0.5,
        max_lines_per_tick: int = 100,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously yields new lines appended to the log file.
        Non-blocking, with strict secret redaction applied to each line.
        """
        if await asyncio.to_thread(self.log_path.exists):
            try:
                self._last_position = await asyncio.to_thread(lambda: self.log_path.stat().st_size)
            except Exception:
                self._last_position = 0

        while not self._stopped:
            try:
                await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                break

            lines, self._last_position = await asyncio.to_thread(
                self._read_chunk, self._last_position, max_lines_per_tick
            )
            for line in lines:
                yield line
