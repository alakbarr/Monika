"""
Startup Watchdog — detects deadlocks during TradingAgent initialization.
Arms early before complex imports and monitors initialization phases.
Dumps all thread tracebacks via faulthandler on timeout and enforces bounded exit.
"""
import faulthandler
import logging
import os
import sys
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("TradingAgent.StartupWatchdog")


class StartupWatchdog:
    """Monitors startup progress with phase leases and faulthandler deadlock diagnostics."""

    def __init__(
        self,
        timeout_seconds: float = 180.0,
        on_deadlock: Optional[Callable[[], None]] = None,
        enforce_exit: Optional[bool] = None,
    ):
        self._timeout = timeout_seconds
        self._deadline = time.time() + timeout_seconds
        self._on_deadlock = on_deadlock
        is_test = ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ)
        self._enforce_exit = enforce_exit if enforce_exit is not None else (not is_test)
        self._complete = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._current_phase = "initialization"
        self._lock = threading.Lock()

    def start(self, timeout_seconds: Optional[float] = None):
        """Start watchdog thread. Safe to call multiple times (idempotent)."""
        with self._lock:
            if timeout_seconds:
                self._timeout = timeout_seconds
                self._deadline = time.time() + timeout_seconds
            if self._started:
                return
            self._started = True

        try:
            faulthandler.enable()
        except Exception:
            pass

        self._thread = threading.Thread(
            target=self._watch,
            daemon=True,
            name="startup-watchdog",
        )
        self._thread.start()
        logger.info(f"[StartupWatchdog] Armed with {self._timeout:.0f}s timeout")

    def report_progress(self, phase: str, lease_seconds: float = 60.0):
        """Extend timeout lease when entering a known slow startup phase (e.g. migrations, MT5 connect)."""
        with self._lock:
            self._current_phase = phase
            self._deadline = max(self._deadline, time.time() + lease_seconds)
        logger.info(f"[StartupWatchdog] Phase '{phase}': extended lease by {lease_seconds:.0f}s")

    def mark_complete(self):
        """Signal that startup completed successfully and disarm watchdog."""
        self._complete.set()
        logger.info("[StartupWatchdog] Startup completed successfully — watchdog disarmed")

    @property
    def is_complete(self) -> bool:
        return self._complete.is_set()

    def _watch(self):
        while not self._complete.is_set():
            now = time.time()
            with self._lock:
                remaining = self._deadline - now

            if remaining <= 0:
                break
            # Sleep in short increments to allow early exit
            time.sleep(min(remaining, 1.0))

        if not self._complete.is_set():
            sys.stderr.write(
                f"\n[CRITICAL FATAL] Startup DEADLOCK detected during phase '{self._current_phase}'! "
                f"Dumping all thread tracebacks:\n"
            )
            sys.stderr.flush()
            try:
                faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            except Exception:
                pass

            is_test = ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ)
            if self._enforce_exit and not is_test:
                # Escort thread ensuring process terminates within 10s even if callbacks hang
                def _escort_kill():
                    time.sleep(10.0)
                    os._exit(75)

                escort = threading.Thread(target=_escort_kill, daemon=True, name="deadlock-escort")
                escort.start()

            if self._on_deadlock is not None:
                try:
                    self._on_deadlock()
                except Exception as e:
                    sys.stderr.write(f"Error in deadlock handler: {e}\n")

            if self._enforce_exit and not is_test:
                os._exit(75)  # EX_TEMPFAIL — signals transient failure to process supervisor


# Global singleton
global_startup_watchdog = StartupWatchdog()


def arm_startup_watchdog(timeout_s: float = 180.0):
    """Early bootstrap hook to arm watchdog before application imports."""
    if ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ):
        return
    global_startup_watchdog.start(timeout_seconds=timeout_s)
