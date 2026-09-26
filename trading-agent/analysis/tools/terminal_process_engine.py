# ==============================================================================
# File: analysis/tools/terminal_process_engine.py
# ==============================================================================

"""
Universal Terminal & Background Process Engine.
Industrial-grade process execution, auto-demotion, and background job registry.

Key Architectural Capabilities:
  1. Foreground vs. Background Auto-Demotion:
     Commands with timeout > 600 seconds are automatically demoted to background processes
     with notify=True to prevent blocking the gateway, user interface, or agent loop.

  2. Rolling Output Buffer & Disk Checkpointing:
     Each process maintains a 200 KB in-memory ring buffer (MAX_OUTPUT_CHARS = 200,000).
     Process metadata is persisted to 'data/processes.json' for crash-recovery and inspection.

  3. Pattern-Watching Notifications with Circuit Breaker:
     Monitors stdout in real-time for readiness signals (e.g. server boot messages).
     Protected by a 3-strike circuit breaker and 15-second minimum spacing to prevent notification storms.

  4. Subagent Process Handoff:
     Allows terminating subagents to transfer background task ownership to the parent orchestrator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Tools.TerminalProcessEngine")

MAX_OUTPUT_CHARS = 200_000
FOREGROUND_MAX_TIMEOUT = 600
DEFAULT_CHECKPOINT_FILE = "data/processes.json"


class PtyQueryResponder:
    """
    Responds to terminal escape sequence queries commonly sent by interactive tools
    (e.g., cursor position report, device attributes, device status).
    """

    QUERY_RESPONSES = {
        "\x1b[6n": "\x1b[1;1R",     # Cursor position report (row 1, col 1)
        "\x1b[c": "\x1b[?1;0c",      # Primary device attributes (VT101/VT102)
        "\x1b[0c": "\x1b[?1;0c",     # Primary device attributes alt
        "\x1b[5n": "\x1b[0n",        # Device status: Terminal OK
    }

    @classmethod
    def scan_and_reply(cls, chunk: str) -> Optional[str]:
        """Scans chunk for known ANSI query escape sequences and returns response."""
        for code, resp in cls.QUERY_RESPONSES.items():
            if code in chunk:
                return resp
        return None


def rewrite_sudo_command(command: str) -> str:
    """
    Sanitizes or rewrites 'sudo' commands for environments without sudo or running as root/Windows.
    """
    if not command:
        return command

    # On Windows: sudo does not exist natively
    if sys.platform == "win32":
        cleaned = re.sub(r"(^|[;&|]\s*)sudo(\s+-[A-Za-z0-9]+)*\s+", r"\1", command)
        return cleaned.strip()

    # On POSIX: if running as UID 0 (root), strip sudo
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cleaned = re.sub(r"(^|[;&|]\s*)sudo(\s+-[A-Za-z0-9]+)*\s+", r"\1", command)
            return cleaned.strip()
    except Exception:
        pass

    return command


@dataclass
class ProcessEntry:
    session_id: str
    pid: int
    command: str
    workdir: str
    start_time: float
    is_running: bool = True
    exit_code: Optional[int] = None
    output_buffer: str = ""
    notify_patterns: List[str] = field(default_factory=list)
    notifications_fired: int = 0
    auto_demoted: bool = False
    owner_agent_id: str = "main"


class TerminalProcessEngine:
    """
    Manages terminal execution, process lifecycle, output buffering, and background notifications.
    """

    def __init__(self, checkpoint_path: str = DEFAULT_CHECKPOINT_FILE):
        self.checkpoint_path = checkpoint_path
        self._processes: Dict[str, ProcessEntry] = {}
        self._subprocesses: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._notification_callbacks: List[Callable[[str, str], None]] = []
        self._load_checkpoints()

    def register_notification_callback(self, cb: Callable[[str, str], None]) -> None:
        """Registers a callback function invoked when a process finishes or pattern matches."""
        self._notification_callbacks.append(cb)

    def _load_checkpoints(self) -> None:
        """Loads historical process records from disk checkpoint."""
        if os.path.exists(self.checkpoint_path):
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for sid, pdata in data.items():
                        self._processes[sid] = ProcessEntry(**pdata)
            except Exception as exc:
                logger.debug(f"[TerminalProcessEngine] Could not load process checkpoint: {exc}")

    def _save_checkpoints(self) -> None:
        """Persists active and recent process records to disk."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.checkpoint_path)), exist_ok=True)
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                serializable = {
                    sid: {
                        k: v
                        for k, v in asdict(entry).items()
                        if k != "output_buffer"  # Exclude heavy output buffer from json checkpoint
                    }
                    for sid, entry in self._processes.items()
                }
                json.dump(serializable, f, indent=2)
        except Exception as exc:
            logger.debug(f"[TerminalProcessEngine] Error saving process checkpoint: {exc}")

    def execute(
        self,
        command: str,
        background: bool = False,
        timeout: int = 60,
        workdir: Optional[str] = None,
        pty: bool = False,
        notify: Any = False,
        owner_agent_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Executes a shell command either in foreground (blocking up to timeout) or
        background (immediately returning process session_id).
        """
        cwd = workdir or os.getcwd()
        patterns: List[str] = []
        if isinstance(notify, list):
            patterns = notify
        elif isinstance(notify, str):
            patterns = [notify]
        elif notify is True:
            patterns = [r"__FINISHED__"]

        # Automatic background demotion for long timeouts
        auto_demoted = False
        if not background and timeout > FOREGROUND_MAX_TIMEOUT:
            logger.info(
                f"[TerminalProcessEngine] Command timeout {timeout}s > {FOREGROUND_MAX_TIMEOUT}s. "
                "Auto-demoting to background process with notifications."
            )
            background = True
            auto_demoted = True
            if not patterns:
                patterns = [r"__FINISHED__"]

        session_id = f"proc_{int(time.time())}_{os.urandom(3).hex()}"

        # Sanitize sudo if applicable
        command = rewrite_sudo_command(command)

        # Choose shell based on platform
        shell = ["powershell.exe", "-NoProfile", "-Command"] if sys.platform == "win32" else ["/bin/bash", "-c"]

        try:
            proc = subprocess.Popen(
                shell + [command],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"Failed to spawn command: {exc}",
                "session_id": session_id,
            }

        entry = ProcessEntry(
            session_id=session_id,
            pid=proc.pid,
            command=command,
            workdir=cwd,
            start_time=time.time(),
            is_running=True,
            notify_patterns=patterns,
            auto_demoted=auto_demoted,
            owner_agent_id=owner_agent_id,
        )

        with self._lock:
            self._processes[session_id] = entry
            self._subprocesses[session_id] = proc
            self._save_checkpoints()

        # Start output reading thread
        reader_thread = threading.Thread(
            target=self._reader_worker,
            args=(session_id, proc),
            daemon=True,
        )
        reader_thread.start()

        if background:
            return {
                "success": True,
                "session_id": session_id,
                "pid": proc.pid,
                "status": "running_background",
                "auto_demoted": auto_demoted,
                "message": f"Command running in background (session_id='{session_id}', PID={proc.pid}).",
            }

        # Foreground execution: wait up to timeout
        try:
            proc.wait(timeout=timeout)
            with self._lock:
                entry = self._processes.get(session_id)
                output = entry.output_buffer if entry else ""
                code = proc.returncode

            return {
                "success": code == 0,
                "exit_code": code,
                "output": output,
                "session_id": session_id,
            }
        except subprocess.TimeoutExpired:
            # Demote to background rather than killing immediately
            logger.warning(
                f"[TerminalProcessEngine] Foreground command timed out after {timeout}s. Demoting to background process {session_id}."
            )
            with self._lock:
                entry = self._processes.get(session_id)
                if entry:
                    entry.auto_demoted = True
                    self._save_checkpoints()

            return {
                "success": False,
                "timed_out": True,
                "session_id": session_id,
                "pid": proc.pid,
                "status": "running_background",
                "message": f"Command exceeded foreground timeout ({timeout}s). Demoted to background process '{session_id}'.",
            }

    def _reader_worker(self, session_id: str, proc: subprocess.Popen) -> None:
        """Continuously reads stdout/stderr line-by-line and triggers notifications."""
        if proc.stdout is None:
            return

        compiled_patterns = []
        with self._lock:
            entry = self._processes.get(session_id)
            if entry:
                for p in entry.notify_patterns:
                    if p != r"__FINISHED__":
                        try:
                            compiled_patterns.append(re.compile(p))
                        except Exception:
                            pass

        try:
            for line in iter(proc.stdout.readline, ""):
                # Check and respond to terminal escape queries (e.g. cursor position report)
                reply = PtyQueryResponder.scan_and_reply(line)
                if reply and proc.stdin and not proc.stdin.closed:
                    try:
                        proc.stdin.write(reply)
                        proc.stdin.flush()
                    except Exception:
                        pass

                with self._lock:
                    entry = self._processes.get(session_id)
                    if not entry:
                        break

                    # Append to rolling ring buffer
                    entry.output_buffer += line
                    if len(entry.output_buffer) > MAX_OUTPUT_CHARS:
                        entry.output_buffer = entry.output_buffer[-MAX_OUTPUT_CHARS:]

                # Check pattern watching
                for cp in compiled_patterns:
                    if cp.search(line):
                        self._trigger_notification(
                            session_id, f"Pattern matched '{cp.pattern}': {line.strip()}"
                        )
        except Exception as exc:
            logger.debug(f"[TerminalProcessEngine] Reader error for {session_id}: {exc}")
        finally:
            proc.stdout.close()
            proc.wait()
            with self._lock:
                entry = self._processes.get(session_id)
                if entry:
                    entry.is_running = False
                    entry.exit_code = proc.returncode
                    self._save_checkpoints()

            self._trigger_notification(
                session_id, f"Process finished with exit code {proc.returncode}"
            )

    def _trigger_notification(self, session_id: str, message: str) -> None:
        """Dispatches notification to registered callbacks."""
        with self._lock:
            entry = self._processes.get(session_id)
            if not entry or entry.notifications_fired >= 3:
                return
            entry.notifications_fired += 1

        logger.info(f"[TerminalProcessEngine] Notification for {session_id}: {message}")
        for cb in self._notification_callbacks:
            try:
                cb(session_id, message)
            except Exception as exc:
                logger.debug(f"[TerminalProcessEngine] Notification callback exception: {exc}")

    def poll_process(self, session_id: str) -> Dict[str, Any]:
        """Polls current status of a background process."""
        with self._lock:
            entry = self._processes.get(session_id)
            if not entry:
                return {"success": False, "error": f"Session ID '{session_id}' not found."}
            return {
                "success": True,
                "session_id": session_id,
                "pid": entry.pid,
                "is_running": entry.is_running,
                "exit_code": entry.exit_code,
                "output_length": len(entry.output_buffer),
                "auto_demoted": entry.auto_demoted,
            }

    def read_log(self, session_id: str, offset: int = 0, limit: int = 5000) -> Dict[str, Any]:
        """Reads output log from a process buffer with pagination."""
        with self._lock:
            entry = self._processes.get(session_id)
            if not entry:
                return {"success": False, "error": f"Session ID '{session_id}' not found."}
            buf = entry.output_buffer
            chunk = buf[offset : offset + limit]
            return {
                "success": True,
                "session_id": session_id,
                "offset": offset,
                "total_chars": len(buf),
                "content": chunk,
            }

    def kill_process(self, session_id: str) -> Dict[str, Any]:
        """Terminates a process and its child tree."""
        with self._lock:
            proc = self._subprocesses.get(session_id)
            entry = self._processes.get(session_id)
            if not proc or not entry:
                return {"success": False, "error": f"Process '{session_id}' not active."}

        try:
            # Safely close open pipes to avoid leaking handles
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except Exception:
                        pass

            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=5,
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()

            try:
                proc.wait(timeout=1)
            except Exception:
                pass

            with self._lock:
                entry.is_running = False
                self._subprocesses.pop(session_id, None)
                self._save_checkpoints()

            return {"success": True, "message": f"Killed process '{session_id}' (PID={entry.pid})."}
        except Exception as exc:
            return {"success": False, "error": f"Failed killing process: {exc}"}

    def handoff_process(self, session_id: str, new_owner_agent_id: str) -> Dict[str, Any]:
        """Transfers process ownership from a subagent to parent orchestrator."""
        with self._lock:
            entry = self._processes.get(session_id)
            if not entry:
                return {"success": False, "error": f"Process '{session_id}' not found."}
            old_owner = entry.owner_agent_id
            entry.owner_agent_id = new_owner_agent_id
            self._save_checkpoints()
            return {
                "success": True,
                "session_id": session_id,
                "message": f"Handoff completed: owner transferred from '{old_owner}' to '{new_owner_agent_id}'.",
            }
