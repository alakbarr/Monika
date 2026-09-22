"""
File: execution/ea_bridge/watchdog.py
PR-16: Dual Heartbeat EA Watchdog for Monika.
Actively monitors MQL5 EA heartbeat and trips safety circuits if the broker EA freezes,
disconnects, or fails to write its heartbeat within threshold.
"""

import asyncio
import logging
import time
from typing import Optional, Callable, Dict, Any

from execution.ea_bridge.heartbeat_writer import HeartbeatManager, EA_STALE_THRESHOLD_SECONDS

logger = logging.getLogger("TradingAgent.Execution.EAWatchdog")


class EAWatchdog:
    """
    Active watchdog monitoring the EA -> Python heartbeat.
    Ensures that MT5 terminal and MQL5 EA are alive and responsive before allowing trade execution.
    """

    def __init__(
        self,
        heartbeat_manager: Optional[HeartbeatManager] = None,
        stale_threshold_seconds: float = EA_STALE_THRESHOLD_SECONDS,
        check_interval_seconds: float = 15.0,
        on_trip_callback: Optional[Callable[[str], Any]] = None,
        on_recover_callback: Optional[Callable[[], Any]] = None,
    ):
        self.hb_manager = heartbeat_manager or HeartbeatManager()
        self.stale_threshold = stale_threshold_seconds
        self.check_interval = check_interval_seconds
        self.on_trip_callback = on_trip_callback
        self.on_recover_callback = on_recover_callback

        self._running = False
        self._stop_event = asyncio.Event()
        self._is_ea_alive = True
        self._last_stale_seconds = 0
        self._consecutive_failures = 0
        self._tripped = False

    @property
    def is_alive(self) -> bool:
        """Returns True if the EA heartbeat is fresh and not tripped."""
        return self._is_ea_alive and not self._tripped

    @property
    def last_stale_seconds(self) -> int:
        return self._last_stale_seconds

    def check_now(self) -> tuple[bool, int]:
        """
        Immediately inspects EA heartbeat freshness.
        Returns:
            (is_healthy: bool, stale_seconds: int)
        """
        alive, stale = self.hb_manager.check_ea_alive()
        self._last_stale_seconds = stale

        if not alive:
            self._consecutive_failures += 1
            self._is_ea_alive = False
            reason = f"EA heartbeat stale ({stale}s > {self.stale_threshold}s)" if stale >= 0 else "EA heartbeat file missing"
            if not self._tripped:
                self._tripped = True
                logger.error(f"[EAWatchdog] TRIP: {reason}")
                self._emit_trip_event(reason)
            return False, stale

        # EA is alive and fresh
        self._consecutive_failures = 0
        self._is_ea_alive = True
        if self._tripped:
            self._tripped = False
            logger.info(f"[EAWatchdog] RECOVER: EA heartbeat restored ({stale}s lag).")
            self._emit_recover_event()

        return True, stale

    async def run_forever(self) -> None:
        """Runs the periodic watchdog loop."""
        self._running = True
        self._stop_event.clear()
        logger.info(f"[EAWatchdog] Started. Monitoring EA heartbeat every {self.check_interval}s.")

        while self._running and not self._stop_event.is_set():
            try:
                self.check_now()
            except Exception as e:
                logger.error(f"[EAWatchdog] Error during heartbeat inspection: {e}")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        """Signals watchdog loop to terminate."""
        self._running = False
        self._stop_event.set()

    def _emit_trip_event(self, reason: str) -> None:
        """Emits circuit breaker trip on EventBus and invokes callback."""
        try:
            from utils.protocol.event_bus import get_event_bus, CircuitBreakerEvent
            bus = get_event_bus()
            bus.publish_nowait(CircuitBreakerEvent(component="MQL5_EA_Bridge", reason=reason))
        except Exception as e:
            logger.debug(f"[EAWatchdog] EventBus notification non-fatal: {e}")

        if self.on_trip_callback:
            try:
                self.on_trip_callback(reason)
            except Exception as e:
                logger.error(f"[EAWatchdog] Error in on_trip_callback: {e}")

    def _emit_recover_event(self) -> None:
        """Emits circuit breaker recovery and invokes callback."""
        if self.on_recover_callback:
            try:
                self.on_recover_callback()
            except Exception as e:
                logger.error(f"[EAWatchdog] Error in on_recover_callback: {e}")
