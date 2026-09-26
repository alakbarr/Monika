# ==============================================================================
# File: logging_observability/dashboard/pty_bridge.py
# ==============================================================================

"""
PTY Console Bridge & Real-Time Terminal WebSocket Coordinator.
Institutional-grade remote terminal observability architecture.

Provides live bidirectional terminal session streaming between the backend execution
environment and the web dashboard UI:
  - Manages isolated PTY sessions with output circular buffers.
  - Integrates PtyQueryResponder to synthesize responses to ANSI escape sequences.
  - Reaps idle and disconnected sessions to protect system memory.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from analysis.tools.environments.pty_query_responder import PtyQueryResponder

logger = logging.getLogger("TradingAgent.Dashboard.PtyBridge")


@dataclass
class PtySession:
    """Represents an active interactive terminal session connected via WebSocket."""
    session_id: str
    created_at: float
    last_active: float
    query_responder: PtyQueryResponder = field(default_factory=PtyQueryResponder)
    _output_buffer: List[str] = field(default_factory=list)
    _max_buffer_lines: int = 2000
    is_closed: bool = False

    def append_output(self, data: str) -> List[bytes]:
        """
        Appends stdout/stderr stream text to session buffer,
        and returns any synthetic responses to write back to process stdin.
        """
        if self.is_closed:
            return []

        self.last_active = time.time()
        self._output_buffer.append(data)
        if len(self._output_buffer) > self._max_buffer_lines:
            self._output_buffer = self._output_buffer[-self._max_buffer_lines:]

        # Process ANSI query sequences
        responses = self.query_responder.process_output(data)
        return responses

    def drain_output(self) -> str:
        """Drains and returns accumulated output buffer."""
        self.last_active = time.time()
        out = "".join(self._output_buffer)
        self._output_buffer.clear()
        return out

    def close(self) -> None:
        self.is_closed = True
        self._output_buffer.clear()


class PtyBridgeManager:
    """Coordinates active PTY console sessions for the dashboard."""

    def __init__(self, default_idle_timeout_sec: float = 3600.0):
        self.default_idle_timeout_sec = default_idle_timeout_sec
        self._sessions: Dict[str, PtySession] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, session_id: Optional[str] = None) -> PtySession:
        """Creates or registers a new PTY bridge session."""
        sid = session_id or str(uuid.uuid4())
        now = time.time()
        session = PtySession(
            session_id=sid,
            created_at=now,
            last_active=now,
        )
        async with self._lock:
            self._sessions[sid] = session
        logger.info(f"[PtyBridge] Created terminal session '{sid}'.")
        return session

    async def get_session(self, session_id: str) -> Optional[PtySession]:
        """Retrieves active session by ID."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """Closes and removes a session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.close()
                logger.info(f"[PtyBridge] Closed session '{session_id}'.")
                return True
        return False

    async def reap_stale_sessions(self, max_idle_sec: Optional[float] = None) -> int:
        """Evicts sessions exceeding idle timeout."""
        timeout = max_idle_sec or self.default_idle_timeout_sec
        now = time.time()
        reaped = 0

        async with self._lock:
            for sid, sess in list(self._sessions.items()):
                if now - sess.last_active > timeout or sess.is_closed:
                    sess.close()
                    self._sessions.pop(sid, None)
                    reaped += 1
                    logger.debug(f"[PtyBridge] Reaped idle session '{sid}'.")

        return reaped


_GLOBAL_PTY_BRIDGE = PtyBridgeManager()


def get_pty_bridge_manager() -> PtyBridgeManager:
    """Return process singleton PtyBridgeManager."""
    return _GLOBAL_PTY_BRIDGE
