# ==============================================================================
# File: execution/backends/local_backend.py
# ==============================================================================

"""
Local Host Terminal Execution Backend.
Institutional-grade engine turn protection architecture.

Executes shell commands directly on the host with process group isolation,
environment variable sanitization, and robust timeout termination for Windows and POSIX.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from analysis.tools.kernel.env_sanitizer import get_sanitized_environment
from execution.backends.base import BaseTerminalBackend
from security.terminal_guard import assert_safe_write_path

logger = logging.getLogger("TradingAgent.Execution.LocalBackend")

_IS_WINDOWS = sys.platform == "win32"


class LocalTerminalBackend(BaseTerminalBackend):
    """Local OS execution backend."""

    def __init__(self, default_cwd: Optional[str] = None):
        self.default_cwd = default_cwd or os.getcwd()

    def execute(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str, int]:
        target_cwd = cwd or self.default_cwd
        sanitized_env = get_sanitized_environment()
        if env:
            sanitized_env.update(env)

        creationflags = 0
        preexec_fn = None
        if _IS_WINDOWS:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            preexec_fn = os.setsid

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=target_cwd,
                env=sanitized_env,
                creationflags=creationflags,
                preexec_fn=preexec_fn,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout, stderr, proc.returncode
        except subprocess.TimeoutExpired:
            logger.warning(f"[LocalBackend] Command timed out after {timeout}s: {cmd[:60]}")
            self._kill_process_tree(proc)
            return "", f"Command timed out after {timeout} seconds.", -1
        except Exception as exc:
            logger.error(f"[LocalBackend] Execution failed: {exc}")
            return "", str(exc), -1

    def _kill_process_tree(self, proc: subprocess.Popen) -> None:
        """Kill the process and all its descendants."""
        try:
            if _IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5.0,
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def read_file(self, path: str, offset: int = 0, limit: int = -1) -> str:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        if offset > 0:
            text = text[offset:]
        if limit >= 0:
            text = text[:limit]
        return text

    def write_file(self, path: str, content: str, append: bool = False) -> bool:
        safe_path = assert_safe_write_path(path)
        p = Path(safe_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8", errors="replace") as f:
            f.write(content)
        return True

    def is_alive(self) -> bool:
        return True

    def close(self) -> None:
        pass
