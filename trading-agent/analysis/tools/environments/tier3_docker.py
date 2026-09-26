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
    """
    Executes untrusted workloads inside an isolated Docker container with persistent session support
    and graceful fallback to Tier 2 Host Subprocess.
    """

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
        self._active_containers: Dict[str, str] = {}  # session_id -> container_name

    def is_available(self) -> bool:
        """Checks if docker CLI is found on the host system."""
        return self._docker_bin is not None

    async def get_or_create_container(self, session_id: str) -> Optional[str]:
        """Ensure a persistent sandbox container exists for the given session."""
        if not self.is_available():
            return None

        container_name = f"monika-sandbox-{session_id}"
        if session_id in self._active_containers:
            return container_name

        try:
            # Check if container is already running
            check_proc = await asyncio.create_subprocess_exec(
                self._docker_bin, "ps", "-q", "-f", f"name={container_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, _ = await check_proc.communicate()
            if stdout_b.strip():
                self._active_containers[session_id] = container_name
                return container_name

            # Remove any dead/stopped container with same name
            rm_proc = await asyncio.create_subprocess_exec(
                self._docker_bin, "rm", "-f", container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await rm_proc.communicate()

            # Start fresh persistent background container
            run_cmd = [
                self._docker_bin,
                "run",
                "-d",
                f"--name={container_name}",
                f"--memory={self.memory_limit}",
                f"--cpus={self.cpu_limit}",
                "--network=none",  # Airgap network isolation
                self.image_name,
                "tail",
                "-f",
                "/dev/null",
            ]
            run_proc = await asyncio.create_subprocess_exec(
                *run_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            run_stdout, _ = await run_proc.communicate()
            if run_proc.returncode == 0:
                self._active_containers[session_id] = container_name
                logger.info(f"[Tier3Docker] Launched persistent sandbox container: {container_name}")
                return container_name
        except Exception as exc:
            logger.debug(f"[Tier3Docker] Failed to start persistent container '{container_name}': {exc}")

        return None

    async def stop_container(self, session_id: str) -> None:
        """Stops and removes the persistent sandbox container for a session."""
        container_name = self._active_containers.pop(session_id, None) or f"monika-sandbox-{session_id}"
        if self.is_available():
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._docker_bin, "rm", "-f", container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                logger.info(f"[Tier3Docker] Terminated sandbox container: {container_name}")
            except Exception as e:
                logger.debug(f"[Tier3Docker] Cleanup container error: {e}")

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout_seconds: float = 30.0,
        env_vars: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
    ) -> ExecutionOutcome:
        if not self.is_available():
            logger.info("[Tier3Docker] Docker not available on host. Falling back to Tier 2 Host Kernel.")
            return await self.fallback_tier.run_command(command, cwd, timeout_seconds, env_vars)

        start_time = time.perf_counter()

        # Try persistent container execution first if session_id provided
        container_name: Optional[str] = None
        if session_id:
            container_name = await self.get_or_create_container(session_id)

        if container_name:
            docker_cmd = [
                self._docker_bin,
                "exec",
                "-i",
                container_name,
                "sh",
                "-c",
                command,
            ]
        else:
            # Ephemeral fallback container
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
        session_id: Optional[str] = None,
    ) -> ExecutionOutcome:
        if not self.is_available():
            return await self.fallback_tier.run_python_code(code, timeout_seconds)

        escaped_code = code.replace("'", "'\"'\"'")
        cmd = f"python3 -c '{escaped_code}'"
        return await self.run_command(cmd, timeout_seconds=timeout_seconds, session_id=session_id)

    def cleanup(self) -> None:
        """Tear down all tracked persistent containers."""
        if not self.is_available() or not self._active_containers:
            return
        for s_id in list(self._active_containers.keys()):
            asyncio.create_task(self.stop_container(s_id))


# Aliases
Tier3DockerContainerEnvironment = Tier3DockerEnvironment

