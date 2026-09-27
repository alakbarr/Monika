# ==============================================================================
# File: analysis/tools/environments/tier2_kernel.py
# ==============================================================================

"""
Tier 2: Host Operating System Guarded Kernel Execution.
Institutional-grade execution isolation architecture.

Runs local subprocesses and Python scripts protected by NT-guard path filters,
Terminal Guard command blocks, environment variable scrubbing, and strict timeouts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from analysis.tools.environments.base_environment import (
    BaseExecutionEnvironment,
    ExecutionOutcome,
)
from security.terminal_guard import validate_command, CommandSecurityViolationError
from utils.security.nt_guard import sanitize_path

logger = logging.getLogger("TradingAgent.Analysis.Tools.Environments.Tier2Kernel")

_SCRUBBED_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "MT5_PASSWORD",
    "DATABASE_URL",
}


class Tier2HostKernelEnvironment(BaseExecutionEnvironment):
    """Executes commands and Python scripts as guarded host subprocesses."""

    def __init__(self, safe_work_dir: Optional[Path] = None):
        self.safe_work_dir = safe_work_dir or Path(os.environ.get("MONIKA_WRITE_SAFE_ROOT", "D:/Monika"))

    def is_available(self) -> bool:
        return True

    def _prepare_sanitized_env(self, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        env = os.environ.copy()
        for k in _SCRUBBED_ENV_KEYS:
            env.pop(k, None)
        if extra_env:
            env.update(extra_env)
        return env

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout_seconds: float = 30.0,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ExecutionOutcome:
        start_time = time.perf_counter()

        # Step 1: Validate command security
        try:
            validate_command(command)
        except CommandSecurityViolationError as sec_err:
            logger.error(f"[Tier2Kernel] Security check rejected command: {sec_err}")
            return ExecutionOutcome(
                exit_code=126,
                stdout="",
                stderr=f"Security Violation: {sec_err}",
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # Step 2: Sanitize working directory
        work_dir = cwd or str(self.safe_work_dir)
        try:
            sanitized_cwd = sanitize_path(work_dir)
        except Exception as pe:
            return ExecutionOutcome(
                exit_code=1,
                stdout="",
                stderr=f"Path Security Violation: {pe}",
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # Step 3: Run subprocess via threadpool for cross-platform event loop immunity
        sanitized_env = self._prepare_sanitized_env(env_vars)
        def _sync_exec() -> Tuple[int, str, str, bool]:
            import subprocess
            try:
                completed = subprocess.run(
                    command,
                    shell=True,
                    cwd=str(sanitized_cwd),
                    env=sanitized_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_seconds,
                )
                return (
                    completed.returncode,
                    completed.stdout.decode("utf-8", errors="replace"),
                    completed.stderr.decode("utf-8", errors="replace"),
                    False,
                )
            except subprocess.TimeoutExpired as te:
                stdout_str = te.stdout.decode("utf-8", errors="replace") if te.stdout else ""
                stderr_str = te.stderr.decode("utf-8", errors="replace") if te.stderr else f"Command timed out after {timeout_seconds} seconds."
                return (-1, stdout_str, stderr_str, True)
            except Exception as e:
                return (1, "", f"Execution error: {type(e).__name__}: {e}", False)

        try:
            exit_code, stdout_str, stderr_str, is_timeout = await asyncio.to_thread(_sync_exec)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExecutionOutcome(
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                execution_time_ms=elapsed_ms,
                is_timeout=is_timeout,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExecutionOutcome(
                exit_code=1,
                stdout="",
                stderr=f"Execution error: {type(exc).__name__}: {exc}",
                execution_time_ms=elapsed_ms,
            )

    async def run_python_code(
        self,
        code: str,
        timeout_seconds: float = 30.0,
    ) -> ExecutionOutcome:
        """Writes code to a temporary script file and runs via python executable."""
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code)
            tmp_path = Path(tmp.name)

        try:
            py_executable = sys.executable
            cmd = f'"{py_executable}" "{tmp_path}"'
            return await self.run_command(cmd, timeout_seconds=timeout_seconds)
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def cleanup(self) -> None:
        pass
