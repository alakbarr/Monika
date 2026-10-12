# ==============================================================================
# File: analysis/tools/environments/base_environment.py
# ==============================================================================

"""
Base Execution Environment Interface for 3-Tier Sandbox.
Institutional-grade execution isolation architecture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ExecutionOutcome:
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    is_timeout: bool = False


class BaseExecutionEnvironment(ABC):
    """Abstract interface for tiered execution environments."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the environment is ready for execution on this host."""
        pass

    @abstractmethod
    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout_seconds: float = 30.0,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ExecutionOutcome:
        """Runs a command inside the isolated environment."""
        pass

    @abstractmethod
    async def run_python_code(
        self,
        code: str,
        timeout_seconds: float = 30.0,
    ) -> ExecutionOutcome:
        """Runs arbitrary or sandboxed Python code."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Release underlying resources or containers."""
        pass
