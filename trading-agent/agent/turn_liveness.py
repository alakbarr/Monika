# ==============================================================================
# File: agent/turn_liveness.py
# ==============================================================================

"""
Turn Liveness Sentinel & Activity Deadlock Watchdog.
Monitors multi-turn tool loops to detect and abort hanging execution threads.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("TradingAgent.Agent.TurnLiveness")


class TurnLivenessWatchdog:
    """
    Guards a running turn against unhandled hangs, deadlocked background tasks,
    or unresponsive upstream network calls.
    """

    def __init__(
        self,
        turn_id: str,
        timeout_seconds: float = 600.0,
        check_interval_seconds: float = 15.0,
        on_hang_detected: Optional[Callable[[str], None]] = None,
    ):
        self.turn_id = turn_id
        self.timeout_seconds = timeout_seconds
        self.check_interval_seconds = check_interval_seconds
        self.on_hang_detected = on_hang_detected
        self._last_activity_time = time.time()
        self._is_active = False
        self._watchdog_task: Optional[asyncio.Task] = None

    def record_activity(self, step_name: str = "") -> None:
        """Updates activity timestamp to postpone hang triggers."""
        self._last_activity_time = time.time()
        if step_name:
            logger.debug(f"[TurnLiveness:{self.turn_id}] Activity heartbeat: {step_name}")

    def start(self) -> None:
        """Starts background liveness inspection."""
        self._is_active = True
        self._last_activity_time = time.time()
        self._watchdog_task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        """Stops the liveness monitor."""
        self._is_active = False
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()

    async def _monitor_loop(self) -> None:
        while self._is_active:
            try:
                await asyncio.sleep(self.check_interval_seconds)
                idle_duration = time.time() - self._last_activity_time
                if idle_duration > self.timeout_seconds:
                    logger.error(
                        f"[TurnLiveness] Turn {self.turn_id} deadlocked! "
                        f"No activity for {idle_duration:.1f}s (limit: {self.timeout_seconds:.1f}s)"
                    )
                    if self.on_hang_detected:
                        self.on_hang_detected(f"Turn {self.turn_id} hung for {idle_duration:.1f}s")
                    break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[TurnLiveness:{self.turn_id}] Watchdog error: {exc}")
