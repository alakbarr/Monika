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
    streaming stalls, or unresponsive upstream network calls.
    Features generation-counter tracking and async context management.
    """

    def __init__(
        self,
        turn_id: str,
        timeout_seconds: float = 600.0,
        stall_timeout_seconds: float = 30.0,
        check_interval_seconds: float = 5.0,
        on_hang_detected: Optional[Callable[[str], None]] = None,
    ):
        self.turn_id = turn_id
        self.timeout_seconds = timeout_seconds
        self.stall_timeout_seconds = stall_timeout_seconds
        self.check_interval_seconds = check_interval_seconds
        self.on_hang_detected = on_hang_detected
        self._last_activity_time = time.time()
        self._generation_counter = 0
        self._last_checked_gen = 0
        self._last_gen_advance_time = time.time()
        self._is_active = False
        self._watchdog_task: Optional[asyncio.Task] = None

    @property
    def generation(self) -> int:
        """Current generation progress counter."""
        return self._generation_counter

    def advance_generation(self, count: int = 1) -> int:
        """Advance the generation counter when tokens or chunks arrive."""
        now = time.time()
        self._generation_counter += count
        self._last_gen_advance_time = now
        self._last_activity_time = now
        return self._generation_counter

    def record_activity(self, step_name: str = "", chunk_len: int = 1) -> None:
        """Updates activity timestamp and generation counter to postpone hang triggers."""
        now = time.time()
        self._last_activity_time = now
        if chunk_len > 0:
            self._generation_counter += chunk_len
            self._last_gen_advance_time = now
        if step_name:
            logger.debug(f"[TurnLiveness:{self.turn_id}] Activity heartbeat: {step_name} (gen={self._generation_counter})")

    def start(self) -> None:
        """Starts background liveness inspection."""
        self._is_active = True
        now = time.time()
        self._last_activity_time = now
        self._last_gen_advance_time = now
        self._last_checked_gen = self._generation_counter
        self._watchdog_task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        """Stops the liveness monitor."""
        self._is_active = False
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()

    async def __aenter__(self) -> "TurnLivenessWatchdog":
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    async def _monitor_loop(self) -> None:
        while self._is_active:
            try:
                await asyncio.sleep(self.check_interval_seconds)
                now = time.time()
                idle_duration = now - self._last_activity_time

                # 1. Total dead-stall check
                if idle_duration > self.timeout_seconds:
                    msg = (
                        f"[TurnLiveness] Turn {self.turn_id} deadlocked! "
                        f"No activity for {idle_duration:.1f}s (limit: {self.timeout_seconds:.1f}s)"
                    )
                    logger.error(msg)
                    if self.on_hang_detected:
                        self.on_hang_detected(msg)
                    break

                # 2. Generation progress check (detect streaming / socket freeze)
                if self._generation_counter == self._last_checked_gen:
                    stall_duration = now - self._last_gen_advance_time
                    if stall_duration > self.stall_timeout_seconds:
                        msg = (
                            f"[TurnLiveness] Turn {self.turn_id} generation stalled at gen={self._generation_counter} "
                            f"for {stall_duration:.1f}s (stall threshold: {self.stall_timeout_seconds:.1f}s)"
                        )
                        logger.warning(msg)
                        if self.on_hang_detected:
                            self.on_hang_detected(msg)
                else:
                    self._last_checked_gen = self._generation_counter

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[TurnLiveness:{self.turn_id}] Watchdog error: {exc}")

