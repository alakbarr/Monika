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


import asyncio


async def verify_broker_ping(client, timeout: float = 8.0) -> bool:
    """Verify broker connection and terminal responsiveness."""
    if not client:
        return False
    try:
        if hasattr(client, "is_connected") and asyncio.iscoroutinefunction(client.is_connected):
            connected = await asyncio.wait_for(client.is_connected(), timeout=timeout)
            if not connected:
                return False
        if hasattr(client, "get_account_info"):
            fn = client.get_account_info
            res = await asyncio.wait_for(fn(), timeout=timeout) if asyncio.iscoroutinefunction(fn) else fn()
            return bool(res)
        return True
    except Exception as e:
        logger.warning(f"[StartupWatchdog] Broker ping check failed: {e}")
        return False


async def verify_data_feed_freshness(client, symbols: list, max_stale_sec: float = 600.0) -> dict:
    """Verify that market data feeds are active and returning valid quotes."""
    results = {}
    if not client or not symbols:
        return results

    now = time.time()
    for sym in symbols[:5]:
        try:
            if hasattr(client, "get_current_price"):
                fn = client.get_current_price
                quote = await asyncio.wait_for(fn(sym), timeout=5.0) if asyncio.iscoroutinefunction(fn) else fn(sym)
                if quote and isinstance(quote, dict):
                    ask = float(quote.get("ask") or 0.0)
                    bid = float(quote.get("bid") or 0.0)
                    fetched_at = float(quote.get("fetched_at") or now)
                    is_fresh = (ask > 0 and bid > 0) and ((now - fetched_at) < max_stale_sec)
                    results[sym] = is_fresh
                else:
                    results[sym] = False
            else:
                results[sym] = True
        except Exception as e:
            logger.debug(f"[StartupWatchdog] Feed check for {sym} failed: {e}")
            results[sym] = False
    return results


async def run_cold_start_preflight(agent, max_wait_sec: float = 30.0) -> dict:
    """
    PR-22: Cold-Start Pre-Flight Verification before enabling schedulers.
    Runs broker ping, position reconciliation, and data feed freshness checks.
    """
    summary = {
        "broker_ping": False,
        "positions_reconciled": False,
        "feed_freshness": {},
        "ready": False,
    }

    watchdog = global_startup_watchdog

    # 1. Broker Ping
    watchdog.report_progress("broker_ping", lease_seconds=20.0)
    broker_client = getattr(agent, "mt5_client", None)
    if not broker_client and hasattr(agent, "execution_service") and agent.execution_service:
        broker_client = getattr(agent.execution_service, "mt5", None)

    is_alive = await verify_broker_ping(broker_client)
    summary["broker_ping"] = is_alive or agent.dry_run

    # 2. Position Reconciliation
    watchdog.report_progress("position_reconciliation", lease_seconds=30.0)
    try:
        if agent.execution_service:
            await agent.execution_service.sync_positions()
            if hasattr(agent.execution_service, "reconcile_inflight_orders"):
                await agent.execution_service.reconcile_inflight_orders()
        summary["positions_reconciled"] = True
    except Exception as e:
        logger.warning(f"[StartupWatchdog] Position reconciliation non-fatal: {e}")
        summary["positions_reconciled"] = agent.dry_run

    # 3. Data Feed Freshness
    watchdog.report_progress("data_feed_freshness", lease_seconds=20.0)
    universe = agent.settings.get("trading", {}).get("asset_universe", ["EURUSD", "USDJPY", "XAUUSD"])
    feeds = await verify_data_feed_freshness(broker_client, universe)
    summary["feed_freshness"] = feeds

    # Determine readiness
    summary["ready"] = summary["broker_ping"] and summary["positions_reconciled"]
    watchdog.report_progress("schedulers_arming", lease_seconds=30.0)
    return summary

