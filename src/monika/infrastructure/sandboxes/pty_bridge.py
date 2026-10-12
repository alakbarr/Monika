# ==============================================================================
# Package: monika.infrastructure.sandboxes
# File: pty_bridge.py
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
from dataclasses import dataclass, field
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional
import uuid

from monika.application.analysis.tools.environments.pty_query_responder import PtyQueryResponder

logger = logging.getLogger("Monika.Infrastructure.Sandboxes.PtyBridge")


@dataclass
class PtySession:
    """Represents an active interactive terminal session connected via WebSocket."""
    session_id: str
    created_at: float
    last_active: float
    cols: int = 80
    rows: int = 24
    process: Optional[asyncio.subprocess.Process] = None
    query_responder: PtyQueryResponder = field(default_factory=PtyQueryResponder)
    _output_buffer: List[str] = field(default_factory=list)
    _max_buffer_lines: int = 2000
    _input_line_buffer: str = field(default="")
    is_closed: bool = False
    _h_pc: Any = None

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

    def get_history(self) -> str:
        """Returns the full accumulated terminal history buffer without clearing it."""
        return "".join(self._output_buffer)

    def drain_output(self) -> str:
        """Drains and returns accumulated output buffer."""
        self.last_active = time.time()
        out = "".join(self._output_buffer)
        self._output_buffer.clear()
        return out

    async def resize(self, cols: int, rows: int) -> None:
        """Resizes terminal dimensions and synchronizes ConPTY if attached."""
        self.cols = max(10, min(cols, 500))
        self.rows = max(5, min(rows, 200))
        self.last_active = time.time()

        if self._h_pc is not None and sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                class COORD(ctypes.Structure):
                    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]
                coord = COORD(self.cols, self.rows)
                ctypes.windll.kernel32.ResizePseudoConsole(self._h_pc, coord)
            except Exception as e:
                logger.debug(f"[PtySession] ResizePseudoConsole error: {e}")

    async def _log_security_violation(self, command: str, reason: str) -> None:
        """Asynchronously persist security violation audit record to database."""
        try:
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.repositories.activity_log_repository import ActivityLogRepository
            async with get_session() as session:
                repo = ActivityLogRepository(session)
                await repo.log_activity(
                    category="SECURITY",
                    description=f"TerminalGuard blocked prohibited command: {command[:200]} ({reason})",
                    actor=f"pty:{self.session_id[:8]}",
                )
                await session.commit()
        except Exception as log_err:
            logger.debug(f"[PtySession] Failed to log terminal security violation: {log_err}")

    async def write_input(self, data: str) -> None:
        """Writes user input/keystrokes to the underlying subprocess stdin with TerminalGuard security enforcement."""
        self.last_active = time.time()
        if not self.process or not self.process.stdin or self.is_closed:
            return

        # Check for Enter/Return execution trigger
        if "\r" in data or "\n" in data:
            candidate_line = (self._input_line_buffer + data).strip()
            self._input_line_buffer = ""

            from monika.core.security.terminal_guard import is_hardline_blocked_command
            is_blocked, reason = is_hardline_blocked_command(candidate_line)
            if is_blocked:
                logger.warning(
                    f"[PtySession] Prohibited command blocked by TerminalGuard in session '{self.session_id}': {candidate_line} ({reason})"
                )
                # Send SIGINT (Ctrl+C) to cancel line execution in shell
                try:
                    self.process.stdin.write(b"\x03")
                    await self.process.stdin.drain()
                except Exception:
                    pass

                # Emit visual red warning back to user terminal output buffer
                alert_banner = (
                    f"\r\n\x1b[31;1m[SECURITY ALERT] Command execution blocked by TerminalGuard:\x1b[0m\r\n"
                    f"\x1b[33mReason: {reason}\x1b[0m\r\n"
                    f"\x1b[90mCommand: {candidate_line}\x1b[0m\r\n\r\n"
                )
                self._output_buffer.append(alert_banner)
                asyncio.create_task(self._log_security_violation(candidate_line, reason))
                return
        else:
            self._input_line_buffer += data
            if len(self._input_line_buffer) > 4096:
                self._input_line_buffer = self._input_line_buffer[-4096:]

        try:
            self.process.stdin.write(data.encode("utf-8"))
            await self.process.stdin.drain()
        except Exception as e:
            logger.debug(f"[PtySession] Stdin write error: {e}")

    async def close_process(self) -> None:
        """Terminate underlying subprocess cleanly."""
        self.is_closed = True
        if self._h_pc is not None and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.ClosePseudoConsole(self._h_pc)
            except Exception:
                pass
            self._h_pc = None

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def close(self) -> None:
        self.is_closed = True
        self._output_buffer.clear()


class PtyBridgeManager:
    """Coordinates active PTY console sessions for the dashboard."""

    def __init__(self, default_idle_timeout_sec: float = 3600.0):
        self.default_idle_timeout_sec = default_idle_timeout_sec
        self._sessions: Dict[str, PtySession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_session(
        self, session_id: Optional[str] = None, cols: int = 80, rows: int = 24
    ) -> PtySession:
        """Retrieves existing active session or creates a new one with session preservation."""
        sid = session_id or str(uuid.uuid4())
        async with self._lock:
            existing = self._sessions.get(sid)
            if existing and not existing.is_closed:
                return existing
        return await self.create_session(session_id=sid, cols=cols, rows=rows)

    async def create_session(
        self, session_id: Optional[str] = None, cols: int = 80, rows: int = 24
    ) -> PtySession:
        """Creates or registers a new PTY bridge session with an OS shell subprocess."""
        sid = session_id or str(uuid.uuid4())
        now = time.time()

        shell_cmd = "powershell.exe -NoLogo" if sys.platform == "win32" else "/bin/bash"
        proc = None
        try:
            # Whitelist safe system environment variables to prevent secret leakage
            safe_vars = {
                "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
                "USERPROFILE", "HOMEPATH", "HOMEDRIVE", "PSMODULEPATH",
                "LANG", "LC_ALL", "SHELL", "HOME", "USER", "LOGNAME",
            }
            env = {k: v for k, v in os.environ.items() if k.upper() in safe_vars}
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["COLUMNS"] = str(cols)
            env["LINES"] = str(rows)
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=os.getcwd(),
                env=env,
            )
        except Exception as e:
            logger.warning(f"[PtyBridge] Failed to spawn shell '{shell_cmd}': {e}")

        session = PtySession(
            session_id=sid,
            created_at=now,
            last_active=now,
            cols=cols,
            rows=rows,
            process=proc,
        )
        async with self._lock:
            self._sessions[sid] = session
        logger.info(f"[PtyBridge] Created terminal session '{sid}' (PID: {proc.pid if proc else 'none'}).")
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
                await session.close_process()
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
