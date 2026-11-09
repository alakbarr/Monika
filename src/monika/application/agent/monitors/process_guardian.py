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
import traceback
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("TradingAgent.ProcessGuardian")

DEFAULT_GUARDIAN_PORT = 8001
HEARTBEAT_STALE_THRESHOLD_SECONDS = 240.0


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


def clear_stale_heartbeat_kill_flag(flag_path: Optional[Path] = None) -> bool:
    """
    Inspect disk kill switch flag. If it was generated solely due to a transient process
    heartbeat staleness / hang ('HeartbeatStale_*'), archive it to guardian_restart.json
    and remove the kill flag so Monika can restart safely without false liquidation.
    Financial kill switch flags (DrawdownMonitor, MarginMonitor, Manual, etc.) or
    malformed files remain untouched (fail-closed).
    """
    target_flag = flag_path if flag_path is not None else _get_kill_flag_path()
    if not target_flag.exists():
        return False
    try:
        content = target_flag.read_text(encoding="utf-8").strip()
        payload = json.loads(content)
        source = str(payload.get("source", ""))
        if source.startswith("HeartbeatStale_"):
            restart_path = _get_data_dir() / "guardian_restart.json"
            restart_path.write_text(
                json.dumps(
                    {
                        "source": source,
                        "archived_timestamp": time.time(),
                        "original_payload": payload,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            target_flag.unlink(missing_ok=True)
            logger.warning(
                f"[ProcessGuardian] Cleared stale HeartbeatStale flag from previous process hang ({source}). "
                f"Archived diagnostic state to {restart_path}"
            )
            return True
        else:
            logger.critical(
                f"[ProcessGuardian] Active financial/manual kill switch flag detected ({source}); "
                "preserving flag (fail-closed)."
            )
            return False
    except Exception as e:
        logger.critical(
            f"[ProcessGuardian] Unparseable kill switch flag detected at {target_flag}; "
            f"preserving flag for financial safety (fail-closed): {e}"
        )
        return False


class GuardianRequestHandler(http.server.BaseHTTPRequestHandler):
    """Lightweight HTTP request handler for Guardian emergency endpoints."""

    primary_pid: Optional[int] = None
    shutdown_flag: Optional[threading.Event] = None
    stale_threshold: float = HEARTBEAT_STALE_THRESHOLD_SECONDS

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
        threshold = getattr(self, "stale_threshold", HEARTBEAT_STALE_THRESHOLD_SECONDS)
        if hb_path.exists():
            try:
                last_hb = float(hb_path.read_text(encoding="utf-8").strip())
                age = round(time.time() - last_hb, 2)
                is_fresh = age < threshold
            except Exception:
                pass

        kill_active = _get_kill_flag_path().exists()

        resp = {
            "status": "healthy",
            "guardian_pid": os.getpid(),
            "primary_pid": self.primary_pid,
            "primary_heartbeat_age_seconds": age,
            "heartbeat_stale_threshold_seconds": threshold,
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
    stale_threshold: float = HEARTBEAT_STALE_THRESHOLD_SECONDS,
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
    handler_class.stale_threshold = stale_threshold

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
    last_resume_grace_until = 0.0

    try:
        while not stop_event.is_set() and not local_stop.is_set():
            t_before_sleep = time.time()
            time.sleep(2.0)
            slept = time.time() - t_before_sleep

            # Detect OS sleep / Modern Standby: if thread was paused for >10s (intended 2s)
            if slept > 10.0:
                logger.warning(
                    f"[GuardianProcess] Detected OS sleep/standby resume (loop slept {slept:.1f}s). "
                    f"Granting {stale_threshold:.0f}s heartbeat grace period."
                )
                last_resume_grace_until = time.time() + stale_threshold
                try:
                    # Re-stamp heartbeat to current time so primary loop has time to wake and continue
                    hb_path.write_text(str(time.time()), encoding="utf-8")
                except Exception:
                    pass
                continue

            # Check primary process heartbeat
            if hb_path.exists():
                try:
                    now = time.time()
                    if now < last_resume_grace_until:
                        continue

                    last_hb = float(hb_path.read_text(encoding="utf-8").strip())
                    age = now - last_hb
                    if age > stale_threshold:
                        logger.critical(
                            f"[GuardianProcess] WARNING: Primary trading loop unresponsive! "
                            f"Heartbeat age: {age:.1f}s > {stale_threshold:.1f}s. "
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
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._last_loop_tick_monotonic: float = time.monotonic()
        self._lag_watchdog_thread: Optional[threading.Thread] = None
        self._lag_watchdog_stop: threading.Event = threading.Event()
        self._running = False

        raw_env_threshold = os.getenv("GUARDIAN_HEARTBEAT_TIMEOUT_SECONDS")
        if raw_env_threshold:
            try:
                resolved_threshold = float(raw_env_threshold)
            except ValueError:
                resolved_threshold = HEARTBEAT_STALE_THRESHOLD_SECONDS
        else:
            guardian_cfg = self.settings.get("guardian") or self.settings.get("system", {}).get("guardian") or {}
            if isinstance(guardian_cfg, dict):
                resolved_threshold = float(
                    guardian_cfg.get("heartbeat_stale_threshold_seconds", HEARTBEAT_STALE_THRESHOLD_SECONDS)
                )
            else:
                resolved_threshold = float(
                    getattr(guardian_cfg, "heartbeat_stale_threshold_seconds", HEARTBEAT_STALE_THRESHOLD_SECONDS)
                )
        self.heartbeat_stale_threshold_seconds = resolved_threshold

    def start(self) -> None:
        """Spawn the independent Guardian process."""
        clear_stale_heartbeat_kill_flag()

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
            args=(self.port, primary_pid, self._stop_event, self.heartbeat_stale_threshold_seconds),
            daemon=True,
            name="guardian-process",
        )
        self._process.start()
        self._running = True
        logger.info(f"[GuardianSupervisor] Guardian child process spawned (PID: {self._process.pid})")

        # Start periodic heartbeat writer directly inside the main asyncio loop
        try:
            loop = asyncio.get_running_loop()
            self._last_loop_tick_monotonic = time.monotonic()
            self._heartbeat_task = self._async_task = loop.create_task(
                self.start_async_heartbeat(),
                name="guardian-async-heartbeat",
            )
            self._lag_watchdog_stop.clear()
            self._lag_watchdog_thread = threading.Thread(
                target=self._lag_watchdog_loop,
                daemon=True,
                name="event-loop-lag-watchdog",
            )
            self._lag_watchdog_thread.start()
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
            tmp_path = hb_path.with_name(f"{hb_path.name}.tmp")
            tmp_path.write_text(str(time.time()), encoding="utf-8")
            tmp_path.replace(hb_path)
        except Exception:
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
            self._last_loop_tick_monotonic = time.monotonic()
            self._write_heartbeat()
            if stop_event:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                    break
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(5.0)

    def _lag_watchdog_loop(self) -> None:
        """Background watchdog thread monitoring main asyncio event-loop lag."""
        last_dump_time = 0.0
        while self._running and not self._lag_watchdog_stop.is_set():
            self._lag_watchdog_stop.wait(5.0)
            if not self._running or self._lag_watchdog_stop.is_set():
                break
            lag = time.monotonic() - self._last_loop_tick_monotonic
            now = time.monotonic()
            if lag > 30.0 and (now - last_dump_time) > 30.0:
                last_dump_time = now
                main_thread_id = threading.main_thread().ident
                frames = sys._current_frames()
                if main_thread_id is not None and main_thread_id in frames:
                    stack_str = "".join(traceback.format_stack(frames[main_thread_id]))
                else:
                    stack_str = "Main thread not found in active frames"
                logger.warning(
                    f"[GuardianSupervisor] Event loop lag detected ({lag:.1f}s) — main thread stack:\n{stack_str}"
                )

    def stop(self) -> None:
        """Signal and join the Guardian child process."""
        self._running = False
        self._lag_watchdog_stop.set()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if hasattr(self, "_async_task") and self._async_task and not self._async_task.done():
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
    "clear_stale_heartbeat_kill_flag",
    "trigger_emergency_kill",
    "GuardianRequestHandler",
    "GuardianSupervisor",
]
