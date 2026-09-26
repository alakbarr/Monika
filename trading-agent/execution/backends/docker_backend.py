# ==============================================================================
# File: execution/backends/docker_backend.py
# ==============================================================================

"""
Docker Container Execution Backend.
Institutional-grade engine turn protection architecture.

Executes shell commands and file manipulations inside an isolated Docker container,
providing full system sandboxing for untrusted code execution.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from execution.backends.base import BaseTerminalBackend

logger = logging.getLogger("TradingAgent.Execution.DockerBackend")


class DockerTerminalBackend(BaseTerminalBackend):
    """Containerized execution backend using Docker."""

    def __init__(
        self,
        container_name_or_id: str = "monika_sandbox",
        image: str = "python:3.11-slim",
        auto_start: bool = True,
    ):
        self.container_id = container_name_or_id
        self.image = image
        self.auto_start = auto_start
        self._docker_bin = shutil.which("docker")

    def is_docker_available(self) -> bool:
        """Check if Docker CLI is present and daemon responds."""
        if not self._docker_bin:
            return False
        try:
            res = subprocess.run(
                [self._docker_bin, "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            )
            return res.returncode == 0
        except Exception:
            return False

    def is_alive(self) -> bool:
        if not self.is_docker_available():
            return False
        try:
            res = subprocess.run(
                [self._docker_bin, "inspect", "-f", "{{.State.Running}}", self.container_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3.0,
            )
            return res.stdout.strip().lower() == "true"
        except Exception:
            return False

    def execute(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str, int]:
        if not self.is_docker_available():
            return "", "Docker daemon is not available on host system.", -1

        exec_cmd = [self._docker_bin, "exec"]
        if cwd:
            exec_cmd.extend(["-w", cwd])
        if env:
            for k, v in env.items():
                exec_cmd.extend(["-e", f"{k}={v}"])

        exec_cmd.extend([self.container_id, "sh", "-c", cmd])

        try:
            proc = subprocess.Popen(
                exec_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout, stderr, proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            return "", f"Docker execution timed out after {timeout} seconds.", -1
        except Exception as exc:
            return "", str(exc), -1

    def read_file(self, path: str, offset: int = 0, limit: int = -1) -> str:
        stdout, stderr, code = self.execute(f"cat '{path}'")
        if code != 0:
            raise FileNotFoundError(f"Failed to read file in container: {stderr}")
        text = stdout
        if offset > 0:
            text = text[offset:]
        if limit >= 0:
            text = text[:limit]
        return text

    def write_file(self, path: str, content: str, append: bool = False) -> bool:
        redir = ">>" if append else ">"
        # Escape single quotes safely
        safe_content = content.replace("'", "'\\''")
        cmd = f"printf '%s' '{safe_content}' {redir} '{path}'"
        _, stderr, code = self.execute(cmd)
        if code != 0:
            logger.error(f"[DockerBackend] Write failed: {stderr}")
            return False
        return True

    def close(self) -> None:
        pass
