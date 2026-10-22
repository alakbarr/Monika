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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.SessionPlan")


class SessionPlan:
    """Task-scoped plan manager tied to a session ID."""

    # Singleton in-memory store per session (not persisted to DB by design,
    # aligning with the session-scoped chat memory contract).
    _store: Dict[str, Dict[str, Any]] = {}

    def __init__(self, session_id: str, goal: Optional[str] = None):
        self.session_id = session_id or "default"
        if self.session_id not in self._store:
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
        self._state["tasks"].append(entry)
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[SessionPlan] Added task to session={self.session_id}: {entry['task']}")
        return entry

    def update_task(self, task_index: int, status: str, note: Optional[str] = None) -> bool:
        if not (0 <= task_index < len(self._state["tasks"])):
            return False
        self._state["tasks"][task_index]["status"] = str(status).strip().upper()
        if note:
            self._state["tasks"][task_index]["note"] = str(note).strip()[:500]
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_plan(self) -> Dict[str, Any]:
        return dict(self._state)

    def summary_text(self) -> str:
        tasks = self._state.get("tasks", [])
        lines = [
            f"PLAN[{self.session_id}]: goal={self._state.get('goal', 'N/A')}",
            f"Status: {self._state.get('status', 'N/A')} | Tasks: {len(tasks)}",
        ]
        for i, t in enumerate(tasks[-5:], start=1):
            lines.append(f"  {i}. [{t['status']}] {t['task']} (priority={t.get('priority', 'NORMAL')})")
        return " | ".join(lines)

    def clear(self) -> None:
        if self.session_id in self._store:
            self._store.pop(self.session_id, None)
        logger.info(f"[SessionPlan] Cleared session plan: {self.session_id}")
