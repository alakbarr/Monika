# ==============================================================================
# File: execution/backends/base.py
# ==============================================================================

"""
Base Terminal Backend Interface.
Institutional-grade engine turn protection architecture.

Defines the contract for terminal command execution, file operations,
and lifecycle management across diverse environments (Local, Docker, Cloud).
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional, Tuple


class BaseTerminalBackend(abc.ABC):
    """Abstract interface for execution environments."""

    @abc.abstractmethod
    def execute(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str, int]:
        """
        Execute command string in the environment.
        Returns: (stdout, stderr, exit_code)
        """
        pass

    @abc.abstractmethod
    def read_file(self, path: str, offset: int = 0, limit: int = -1) -> str:
        """Read content of a file from the environment."""
        pass

    @abc.abstractmethod
    def write_file(self, path: str, content: str, append: bool = False) -> bool:
        """Write text content to a file in the environment."""
        pass

    @abc.abstractmethod
    def is_alive(self) -> bool:
        """Check if backend runtime is ready and reachable."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Clean up backend resources."""
        pass
