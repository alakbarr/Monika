# ==============================================================================
# File: analysis/tools/environments/tier3_docker.py
# ==============================================================================

"""
Tier 3: Isolated Docker/OCI Container Execution Environment.
Institutional-grade execution isolation architecture.

Runs untrusted workloads inside an ephemeral, resource-constrained container
with complete network and filesystem sandboxing. Gracefully falls back if Docker is offline.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from typing import Any, Dict, Optional

from analysis.tools.environments.base_environment import (
    BaseExecutionEnvironment,
    ExecutionOutcome,
)
from analysis.tools.environments.tier2_kernel import Tier2HostKernelEnvironment

logger = logging.getLogger("TradingAgent.Analysis.Tools.Environments.Tier3Docker")


class Tier3DockerEnvironment(BaseExecutionEnvironment):
    """Executes workloads inside an isolated Docker container with fallback to Tier 2."""

    def __init__(
        self,
        image_name: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
        fallback_tier: Optional[BaseExecutionEnvironment] = None,
    ):
        self.image_name = image_name
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.fallback_tier = fallback_tier or Tier2HostKernelEnvironment()
        self._docker_bin = shutil.which("docker")

    def is_available(self) -> bool:
        """Checks if docker CLI is found on the host system."""
        return self._docker_bin is not None

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout_seconds: float = 30.0,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ExecutionOutcome:
        if not self.is_available():
            logger.info("[Tier3Docker] Docker not available on host. Falling back to Tier 2 Host Kernel.")
            return await self.fallback_tier.run_command(command, cwd, timeout_seconds, env_vars)

        start_time = time.perf_counter()
        docker_cmd = [
            self._docker_bin,
            "run",
            "--rm",
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpu_limit}",
            "--network=none",  # Full airgap network isolation
            self.image_name,
            "sh",
            "-c",
            command,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            return ExecutionOutcome(
                exit_code=proc.returncode if proc.returncode is not None else 0,
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
                execution_time_ms=elapsed_ms,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return ExecutionOutcome(
                exit_code=-1,
                stdout="",
                stderr=f"Docker container timed out after {timeout_seconds} seconds.",
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
                is_timeout=True,
            )
        except Exception as e:
            logger.warning(f"[Tier3Docker] Docker invocation error: {e}. Falling back to Tier 2.")
            return await self.fallback_tier.run_command(command, cwd, timeout_seconds, env_vars)

    async def run_python_code(
        self,
        code: str,
        timeout_seconds: float = 30.0,
    ) -> ExecutionOutcome:
        if not self.is_available():
            return await self.fallback_tier.run_python_code(code, timeout_seconds)

        escaped_code = code.replace("'", "'\"'\"'")
        cmd = f"python3 -c '{escaped_code}'"
        return await self.run_command(cmd, timeout_seconds=timeout_seconds)

    def cleanup(self) -> None:
        pass
