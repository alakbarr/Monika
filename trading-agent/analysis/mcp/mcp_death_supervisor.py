# ==============================================================================
# File: analysis/mcp/mcp_death_supervisor.py
# ==============================================================================

"""
Zero-Polling Orphan Process Supervisor for MCP Server Subprocesses.
Ensures external MCP servers are cleanly killed when Monika shuts down,
receives SIGINT/SIGTERM, or encounters a fatal crash.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
from typing import Set

logger = logging.getLogger("TradingAgent.MCP.DeathSupervisor")


class McpDeathSupervisor:
    """
    Tracks and guarantees termination of MCP child processes to prevent orphaned daemons.
    """

    _tracked_pids: Set[int] = set()
    _installed: bool = False

    @classmethod
    def register_process(cls, pid: int) -> None:
        """Registers a child PID for automatic termination on exit."""
        if not pid or pid <= 0:
            return
        cls._install_hooks_if_needed()
        cls._tracked_pids.add(pid)
        logger.debug(f"[McpDeathSupervisor] Registered PID {pid} for orphan protection.")

    @classmethod
    def unregister_process(cls, pid: int) -> None:
        """Unregisters a cleanly stopped process."""
        cls._tracked_pids.discard(pid)

    @classmethod
    def _install_hooks_if_needed(cls) -> None:
        """Installs atexit and signal handlers once."""
        if cls._installed:
            return
        cls._installed = True
        atexit.register(cls.kill_all_orphans)

        # Register signals if running in main thread
        try:
            signal.signal(signal.SIGINT, cls._signal_handler)
            signal.signal(signal.SIGTERM, cls._signal_handler)
        except (ValueError, AttributeError):
            pass

    @classmethod
    def _signal_handler(cls, signum, frame):
        """Signal handler terminating all children before process exit."""
        logger.info(f"[McpDeathSupervisor] Signal {signum} received. Terminating child MCP processes...")
        cls.kill_all_orphans()
        sys.exit(128 + signum)

    @classmethod
    def kill_all_orphans(cls) -> None:
        """Kills all registered child processes immediately."""
        pids = list(cls._tracked_pids)
        cls._tracked_pids.clear()
        for pid in pids:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        timeout=3,
                    )
                else:
                    os.kill(pid, signal.SIGKILL)
                logger.debug(f"[McpDeathSupervisor] Cleaned up child PID {pid}")
            except Exception as exc:
                logger.debug(f"[McpDeathSupervisor] Error terminating PID {pid}: {exc}")
