# ==============================================================================
# File: application/planning/session_plan.py
# ==============================================================================

"""
Session-scoped planning mechanism for trading analysis tasks.

Links to the working scratchpad (`memory/working_scratchpad.py`) so that
per-session plans can reference active symbol-level scratchpads and stay
within the bounded chat-memory budget (~8k tokens).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.SessionPlan")


class SessionPlan:
    """Task-scoped plan manager tied to a session ID."""

    # Singleton in-memory store per session with concurrency lock and bounded capacity
    _store: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()
    _MAX_SESSIONS = 200

    def __init__(self, session_id: str, goal: Optional[str] = None):
        self.session_id = session_id or "default"
        with self._lock:
            if self.session_id not in self._store:
                if len(self._store) >= self._MAX_SESSIONS:
                    # Evict oldest 50 sessions
                    oldest_keys = list(self._store.keys())[:50]
                    for k in oldest_keys:
                        self._store.pop(k, None)

                self._store[self.session_id] = {
                    "session_id": self.session_id,
                    "goal": (goal or "").strip(),
                    "tasks": [],
                    "status": "ACTIVE",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            self._state = self._store[self.session_id]

    @classmethod
    def get_or_create(cls, session_id: str, goal: Optional[str] = None) -> "SessionPlan":
        return cls(session_id, goal)

    def add_task(self, task: str, priority: str = "NORMAL") -> Dict[str, Any]:
        entry = {
            "task": str(task).strip(),
            "priority": str(priority).strip().upper(),
            "status": "PENDING",
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._state["tasks"].append(entry)
            self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[SessionPlan] Added task to session={self.session_id}: {entry['task']}")
        return entry

    def update_task(self, task_index: int, status: str, note: Optional[str] = None) -> bool:
        with self._lock:
            if not (0 <= task_index < len(self._state["tasks"])):
                return False
            self._state["tasks"][task_index]["status"] = str(status).strip().upper()
            if note:
                self._state["tasks"][task_index]["note"] = str(note).strip()[:500]
            self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_plan(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def summary_text(self) -> str:
        with self._lock:
            tasks = list(self._state.get("tasks", []))
            goal = self._state.get("goal", "N/A")
            status = self._state.get("status", "N/A")
        lines = [
            f"PLAN[{self.session_id}]: goal={goal}",
            f"Status: {status} | Tasks: {len(tasks)}",
        ]
        for i, t in enumerate(tasks[-5:], start=1):
            lines.append(f"  {i}. [{t['status']}] {t['task']} (priority={t.get('priority', 'NORMAL')})")
        return " | ".join(lines)

    def clear(self) -> None:
        with self._lock:
            if self.session_id in self._store:
                self._store.pop(self.session_id, None)
        logger.info(f"[SessionPlan] Cleared session plan: {self.session_id}")
