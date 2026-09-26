# ==============================================================================
# File: logging_observability/delegation_live_log.py
# ==============================================================================

"""
Subagent Delegation Live Transcript & Streaming Logger.
Provides real-time disk persistence for subagent progress, tool calls, and LLM thoughts.
Allows parent agents, CLI watchers (tail -f), and web dashboards to monitor
delegated subagents asynchronously with zero locking latency.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Logging.DelegationLiveLog")

DEFAULT_LOG_DIR = Path("trading-agent/logs/subagents")


class LiveTranscriptWriter:
    """
    Appends live events and token chunks to an isolated subagent transcript file.
    Always flushes immediately to ensure live tailing works reliably.
    """

    def __init__(self, subagent_id: str, log_dir: Optional[Path] = None):
        self.subagent_id = subagent_id
        self.log_dir = Path(log_dir or DEFAULT_LOG_DIR).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / f"{self.subagent_id}.jsonl"
        self._lock = threading.Lock()
        self._file = open(self.log_path, "a", encoding="utf-8", buffering=1)  # line buffered

    def emit_event(
        self,
        event_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a structured event: 'start', 'thought', 'tool_call', 'tool_result', 'chunk', 'finish', 'error'.
        """
        payload = {
            "timestamp": time.time(),
            "subagent_id": self.subagent_id,
            "type": event_type,
            "content": content,
            "metadata": metadata or {},
        }
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock:
            if not self._file.closed:
                self._file.write(line)
                self._file.flush()

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read the most recent events from the log file."""
        if not self.log_path.exists():
            return []
        events = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"[LiveTranscriptWriter] Failed reading events from {self.log_path}: {e}")
        return events

    def close(self) -> None:
        """Close log file handle."""
        with self._lock:
            if not self._file.closed:
                try:
                    self._file.flush()
                    self._file.close()
                except Exception:
                    pass

    def __enter__(self) -> LiveTranscriptWriter:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
