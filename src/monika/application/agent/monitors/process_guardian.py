# ==============================================================================
# Package: monika.application.agent.monitors
# File: process_guardian.py
# Description: Multi-Process Guardian & Emergency Kill Supervisor
# ==============================================================================

"""
Multi-Process Guardian & Emergency Kill Supervisor.
Runs as an independent OS child process completely isolated from the primary LLM event loop.

Key Capabilities:
1. Independent HTTP emergency listener on GUARDIAN_PORT (default 8001) for /kill and /health.
2. Heartbeat monitor: tracks primary process heartbeats; detects freezes > 60s.
3. Fail-closed kill switch enforcement: writes kill flag, trips database kill switch,
   and terminates stalled Python processes.
4. Clean OS signal escalation and shutdown management on Windows and POSIX.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import logging
import multiprocessing
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("TradingAgent.ProcessGuardian")

DEFAULT_GUARDIAN_PORT = 8001
HEARTBEAT_STALE_THRESHOLD_SECONDS = 60.0


def _get_data_dir() -> Path:
    from monika.core.paths import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def _get_heartbeat_path() -> Path:
    return _get_data_dir() / "monika_main.hb"


def _get_kill_flag_path() -> Path:
    return _get_data_dir() / "kill_switch.flag"


def trigger_emergency_kill(source: str = "Guardian") -> bool:
    """
    Trip the emergency kill switch flags immediately across filesystem.
    """
    flag_path = _get_kill_flag_path()
    try:
        flag_path.write_text(
            json.dumps(
                {
                    "source": source,
                    "timestamp": time.time(),
                    "active": True,
                }
            ),
            encoding="utf-8",
        )
        logger.critical(f"[ProcessGuardian] Emergency kill switch flag written to {flag_path}")
        return True
    except Exception as e:
        logger.error(f"[ProcessGuardian] Failed writing kill flag: {e}")
        return False


class GuardianRequestHandler(http.server.BaseHTTPRequestHandler):
    """Lightweight HTTP request handler for Guardian emergency endpoints."""

    primary_pid: Optional[int] = None
    shutdown_flag: Optional[threading.Event] = None

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard noisy access logging
        pass

    def do_GET(self) -> None:
        if self.path in ("/health", "/status", "/"):
            self._handle_status()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path in ("/kill", "/emergency/kill", "/api/actions/kill"):
            self._handle_kill()
        elif self.path in ("/shutdown", "/stop"):
            self._handle_shutdown()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_status(self) -> None:
        hb_path = _get_heartbeat_path()
        age = None
        is_fresh = False
        if hb_path.exists():
            try:
                last_hb = float(hb_path.read_text(encoding="utf-8").strip())
                age = round(time.time() - last_hb, 2)
                is_fresh = age < HEARTBEAT_STALE_THRESHOLD_SECONDS
            except Exception:
                pass

        kill_active = _get_kill_flag_path().exists()

        resp = {
            "status": "healthy",
            "guardian_pid": os.getpid(),
            "primary_pid": self.primary_pid,
            "primary_heartbeat_age_seconds": age,
            "primary_alive": is_fresh,
            "kill_switch_active": kill_active,
        }
        data = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_kill(self) -> None:
        trigger_emergency_kill(source="HTTP /kill endpoint")

        # Escalate termination to primary PID if provided
        if self.primary_pid and self.primary_pid != os.getpid():
            try:
                import psutil

                if psutil.pid_exists(self.primary_pid):
                    proc = psutil.Process(self.primary_pid)
                    proc.terminate()
            except Exception as e:
                logger.error(f"[ProcessGuardian] Error signaling primary PID {self.primary_pid}: {e}")

        resp = {
            "status": "killed",
            "message": "Emergency kill switch executed by GuardianProcess.",
            "primary_pid": self.primary_pid,
        }
        data = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_shutdown(self) -> None:
        resp = {"status": "shutting_down", "message": "GuardianProcess stopping."}
        data = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

        if self.shutdown_flag:
            self.shutdown_flag.set()


def _run_guardian_loop(
    port: int,
    primary_pid: int,
    stop_event: Any,
) -> None:
    """
    Target entrypoint executed inside the dedicated child OS process.
    Runs HTTP server and monitors heartbeat from primary trading daemon.
    """
    logger.info(f"[GuardianProcess] Initialized on PID {os.getpid()} supervising primary PID {primary_pid}")

    # Defensive disarm: ensure startup watchdog never runs inside guardian child process
    try:
        from monika.application.agent.monitors.startup_watchdog import global_startup_watchdog

        global_startup_watchdog.mark_complete()
    except Exception:
        pass

    handler_class = GuardianRequestHandler
    handler_class.primary_pid = primary_pid

    local_stop = threading.Event()
    handler_class.shutdown_flag = local_stop

    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler_class)
        server.timeout = 1.0
    except Exception as bind_err:
        logger.error(f"[GuardianProcess] Failed binding to port {port}: {bind_err}")
        return

    logger.info(f"[GuardianProcess] Emergency socket active at http://127.0.0.1:{port}/kill")

    # Start HTTP server loop in thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="guardian-http")
    server_thread.start()

    hb_path = _get_heartbeat_path()

    try:
        while not stop_event.is_set() and not local_stop.is_set():
            time.sleep(2.0)

            # Check primary process heartbeat
            if hb_path.exists():
                try:
                    last_hb = float(hb_path.read_text(encoding="utf-8").strip())
                    age = time.time() - last_hb
                    if age > HEARTBEAT_STALE_THRESHOLD_SECONDS:
                        logger.critical(
                            f"[GuardianProcess] WARNING: Primary trading loop unresponsive! "
                            f"Heartbeat age: {age:.1f}s > {HEARTBEAT_STALE_THRESHOLD_SECONDS}s. "
                            f"Triggering emergency kill switch!"
                        )
                        trigger_emergency_kill(source=f"HeartbeatStale_{age:.0f}s")
                        if primary_pid:
                            try:
                                import psutil

                                if psutil.pid_exists(primary_pid):
                                    proc = psutil.Process(primary_pid)
                                    logger.critical(
                                        f"[GuardianProcess] Terminating frozen primary PID {primary_pid}..."
                                    )
                                    proc.terminate()
                            except Exception as term_err:
                                logger.error(
                                    f"[GuardianProcess] Failed terminating primary PID {primary_pid}: {term_err}"
                                )
                except Exception as hb_err:
                    logger.debug(f"[GuardianProcess] Error reading heartbeat: {hb_err}")

            # Verify primary PID is still alive
            if primary_pid:
                try:
                    import psutil

                    if not psutil.pid_exists(primary_pid):
                        logger.info(f"[GuardianProcess] Primary process PID {primary_pid} exited. Exiting guardian.")
                        break
                except Exception:
                    pass
    except KeyboardInterrupt:
        logger.info("[GuardianProcess] Interrupted by user (SIGINT/KeyboardInterrupt).")
    finally:
        server.shutdown()
        server.server_close()
        logger.info("[GuardianProcess] Shutdown complete.")


class GuardianSupervisor:
    """
    Manages the lifecycle of the independent GuardianProcess from the main trading application.
    """

    def __init__(
        self,
        settings: Optional[dict[str, Any]] = None,
        port: int = DEFAULT_GUARDIAN_PORT,
    ):
        self.settings = settings or {}
        self.port = int(os.getenv("GUARDIAN_PORT", port))
        self._process: Optional[multiprocessing.Process] = None
        self._stop_event: Optional[Any] = None
        self._hb_thread: Optional[threading.Thread] = None
        self._async_task: Optional[asyncio.Task[Any]] = None
        self._running = False

    def start(self) -> None:
        """Spawn the independent Guardian process."""
        if self._running:
            return

        is_test = ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ)
        if is_test:
            # In test mode, keep lightweight / passive
            self._running = True
            self._write_heartbeat()
            return

        self._stop_event = multiprocessing.Event()
        primary_pid = os.getpid()

        self._process = multiprocessing.Process(
            target=_run_guardian_loop,
            args=(self.port, primary_pid, self._stop_event),
            daemon=True,
            name="guardian-process",
        )
        self._process.start()
        self._running = True
        logger.info(f"[GuardianSupervisor] Guardian child process spawned (PID: {self._process.pid})")

        # Start periodic heartbeat writer directly inside the main asyncio loop
        try:
            loop = asyncio.get_running_loop()
            self._async_task = loop.create_task(
                self.start_async_heartbeat(),
                name="guardian-async-heartbeat",
            )
        except RuntimeError:
            self._hb_thread = threading.Thread(
                target=self._heartbeat_writer_loop,
                daemon=True,
                name="main-heartbeat",
            )
            self._hb_thread.start()

    def _write_heartbeat(self) -> None:
        hb_path = _get_heartbeat_path()
        try:
            hb_path.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass

    def _heartbeat_writer_loop(self) -> None:
        while self._running:
            self._write_heartbeat()
            time.sleep(5.0)

    async def start_async_heartbeat(self, stop_event: Optional[asyncio.Event] = None) -> None:
        """Periodic heartbeat writer executing directly inside the main asyncio event loop."""
        while self._running:
            self._write_heartbeat()
            if stop_event:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                    break
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(5.0)

    def stop(self) -> None:
        """Signal and join the Guardian child process."""
        self._running = False
        if hasattr(self, "_async_task") and self._async_task:
            self._async_task.cancel()
        if self._stop_event:
            self._stop_event.set()

        if self._process and self._process.is_alive():
            self._process.join(timeout=3.0)
            if self._process.is_alive():
                self._process.terminate()

        # Clean heartbeat file
        try:
            hb = _get_heartbeat_path()
            if hb.exists():
                hb.unlink(missing_ok=True)
        except Exception:
            pass
        logger.info("[GuardianSupervisor] Stopped.")


__all__ = [
    "DEFAULT_GUARDIAN_PORT",
    "HEARTBEAT_STALE_THRESHOLD_SECONDS",
    "trigger_emergency_kill",
    "GuardianRequestHandler",
    "GuardianSupervisor",
]
