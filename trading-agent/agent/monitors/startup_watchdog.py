"""
Startup Watchdog — detects deadlocks during TradingAgent initialization.
If startup doesn't complete within timeout, force-exits to trigger process supervisor restart.
"""
import logging
import os
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger("TradingAgent.StartupWatchdog")


class StartupWatchdog:
    """Monitors startup progress. Force-exits or invokes callback on deadlock."""

    def __init__(
        self,
        timeout_seconds: int = 300,
        on_deadlock: Optional[Callable[[], None]] = None,
    ):
        self._timeout = timeout_seconds
        self._on_deadlock = on_deadlock
        self._complete = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False

    def start(self):
        """Start watchdog thread. Call mark_complete() when initialization finishes."""
        if self._started:
            return
        self._started = True
        logger.info(f"[StartupWatchdog] Armed with {self._timeout}s timeout")
        self._thread = threading.Thread(
            target=self._watch,
            daemon=True,
            name="startup-watchdog",
        )
        self._thread.start()

    def mark_complete(self):
        """Signal that startup completed successfully and disarm watchdog."""
        self._complete.set()
        logger.info("[StartupWatchdog] Startup completed successfully — watchdog disarmed")

    @property
    def is_complete(self) -> bool:
        return self._complete.is_set()

    def _watch(self):
        if not self._complete.wait(timeout=self._timeout):
            logger.critical(
                f"[StartupWatchdog] Startup DEADLOCK detected — "
                f"no completion signal after {self._timeout}s. Action triggered."
            )
            if self._on_deadlock is not None:
                self._on_deadlock()
            else:
                os._exit(75)  # EX_TEMPFAIL — signals transient failure to systemd/supervisor


# Global singleton
global_startup_watchdog = StartupWatchdog()
