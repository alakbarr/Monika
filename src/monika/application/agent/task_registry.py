"""
File: trading-agent/agent/task_registry.py
Background task definitions, lifecycle supervision, and restart supervision.
Extracted from main.py for modularity and maintainability.
"""

import asyncio
import logging
import os
import re
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.TaskRegistry")

CORE_TRADING_TASKS: Set[str] = {
    "MT5Client",
    "MT5HealthMonitor",
    "PositionGuardian",
    "TrailingStop",
    "TrailingStopManager",
    "FlashCrashDetector",
    "Heartbeat",
    "HeartbeatManager",
    "FloatingDrawdownMonitor",
    "MarginGuardian",
    "MarginMonitor",
    "ExecutionService",
    "PositionSupervisor",
    "OrderReconciler",
    "FridayCloseGuardian",
    "CycleScheduler",
    "TickStream",
    "PositionSync",
    "MarketDataScheduler",
    "NewsWatcher",
    "TriggerChecker",
}

CLEAN_SHUTDOWN_FLAG = os.path.join("data", "clean_shutdown.flag")
_EMERGENCY_EXIT_CODE: Optional[int] = None


def get_emergency_exit_code() -> Optional[int]:
    return _EMERGENCY_EXIT_CODE


def set_emergency_exit_code(code: Optional[int]) -> None:
    global _EMERGENCY_EXIT_CODE
    _EMERGENCY_EXIT_CODE = code
    import sys
    for mod_name in ("main", "__main__"):
        main_mod = sys.modules.get(mod_name)
        if main_mod is not None:
            try:
                setattr(main_mod, "_EMERGENCY_EXIT_CODE", code)
            except Exception:
                pass


def mark_clean_shutdown():
    """Write clean shutdown flag file so start scripts know to terminate cleanly."""
    target_paths = [
        CLEAN_SHUTDOWN_FLAG,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "clean_shutdown.flag"),
    ]
    for flag_file in set(target_paths):
        try:
            os.makedirs(os.path.dirname(flag_file), exist_ok=True)
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write(datetime.now(timezone.utc).isoformat())
            logger.info(f"Clean shutdown flag written: {flag_file}")
        except Exception as e:
            logger.warning(f"Failed to write clean shutdown flag to {flag_file}: {e}")


async def _safe_notify_warning(msg: str) -> None:
    try:
        from utils.infra.notifier import AgentNotifier
        notifier = AgentNotifier()
        await asyncio.wait_for(notifier.send_warning(msg), timeout=3.0)
    except Exception as notify_err:
        logger.debug(f"Gagal mengirim warning Telegram: {notify_err}")


async def _safe_notify_critical(msg: str) -> None:
    try:
        from utils.infra.notifier import AgentNotifier
        notifier = AgentNotifier()
        await asyncio.wait_for(notifier.send_critical(msg), timeout=3.0)
    except Exception as notify_err:
        logger.error(f"Gagal mengirim notifikasi fatal Telegram: {notify_err}")


PERMANENT_ERRORS = [
    "AuthenticationError", "invalid_api_key", "API key",
    "Invalid model", "model_not_found",
    "DATABASE_URL", "could not connect to database",
    'relation ".*" does not exist',
    'column ".*" does not exist',
    "No section: ", "No option ", "settings.yaml",
    "CERTIFICATE_VERIFY_FAILED",
    "billing_hard_limit_reached", "quota_exceeded_permanently",
]

LONG_RETRY_ERRORS = [
    "Connection reset by peer",
    "SSL:", "timeout",
    "overloaded", "529", "503",
    "rate_limit",
]


async def _run_with_restart(
    name: str,
    coro_factory,
    shutdown_event: asyncio.Event,
    max_restarts: int = 5,
    base_delay: float = 10.0,
    max_delay: float = 300.0,
):
    """
    Supervises a background task with bulkhead isolation, exponential backoff,
    and fail-closed emergency shutdown for core tasks.
    """
    global _EMERGENCY_EXIT_CODE
    restarts = 0
    last_success_time = _time.monotonic()

    while not shutdown_event.is_set():
        try:
            await coro_factory()
            if shutdown_event.is_set():
                break

            self_obj = getattr(coro_factory, "__self__", None)
            if self_obj is not None:
                if hasattr(self_obj, "_running") and not self_obj._running:
                    logger.info(f"{name} stopped.")
                    break
                if hasattr(self_obj, "is_running"):
                    is_running_val = self_obj.is_running() if callable(self_obj.is_running) else self_obj.is_running
                    if not is_running_val:
                        logger.info(f"{name} stopped.")
                        break

            logger.error(f"{name} exited unexpectedly (but no exception).")
            if _time.monotonic() - last_success_time > 3600:
                restarts = 0
            last_success_time = _time.monotonic()

            restarts += 1
            if restarts > max_restarts:
                if name in CORE_TRADING_TASKS:
                    logger.critical(f"[EMERGENCY] Core trading task {name} exited cleanly {max_restarts} times unexpectedly. Initiating emergency shutdown.")
                    set_emergency_exit_code(2)
                    shutdown_event.set()
                    break
                else:
                    logger.warning(f"[DEGRADED] Auxiliary subsystem {name} exited {max_restarts} times. Isolating with 300s cooldown.")
                    await _safe_notify_warning(
                        f"[PERINGATAN] <b>[DEGRADED] Subsystem {name} exited unexpectedly</b>\n"
                        f"Subsystem auxiliary masuk status DEGRADED dengan cooldown 300s."
                    )
                    restarts = 0
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=300.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

            delay = min(base_delay * (2 ** (restarts - 1)), max_delay)
            logger.warning(f"{name} exited cleanly. Restarting {restarts}/{max_restarts} in {delay}s...")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            logger.info(f"{name} task cancelled.")
            break
        except Exception as e:
            if shutdown_event.is_set():
                break

            error_str = str(e)
            is_permanent = False
            for perm in PERMANENT_ERRORS:
                if perm in error_str or re.search(perm, error_str):
                    is_permanent = True
                    break

            if is_permanent:
                if name in CORE_TRADING_TASKS:
                    error_msg = f"[DARURAT] <b>FATAL CORE TASK CRASH (PERMANENT)</b>\nSubsystem inti <code>{name}</code> gagal permanen:\n{e}\nAplikasi melakukan shutdown darurat."
                    logger.critical(f"[EMERGENCY] Core trading subsystem {name} failed permanently: {e}. Initiating emergency shutdown.")
                    await _safe_notify_critical(error_msg)
                    set_emergency_exit_code(2)
                    shutdown_event.set()
                    break
                else:
                    warn_msg = f"[PERINGATAN] <b>[DEGRADED] Auxiliary subsystem {name} failed (permanent error)</b>\nError: {e}\nSubsystem auxiliary diisolasi (cooldown 300s)."
                    logger.warning(f"[DEGRADED] Auxiliary subsystem {name} failed. Isolating error without shutting down: {e}")
                    await _safe_notify_warning(warn_msg)
                    restarts = 0
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=300.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

            if _time.monotonic() - last_success_time > 3600:
                logger.info(f"{name}: Resetting restart counter (ran > 1h without errors).")
                restarts = 0
            last_success_time = _time.monotonic()

            restarts += 1
            if restarts > max_restarts:
                if name in CORE_TRADING_TASKS:
                    error_msg = f"[DARURAT] <b>FATAL CORE TASK CRASH (MAX RESTARTS EXCEEDED)</b>\nSubsystem inti <code>{name}</code> gagal {max_restarts}x berulang.\nError terakhir: {e}\nAplikasi melakukan shutdown darurat."
                    logger.critical(f"[EMERGENCY] Core trading subsystem {name} exceeded max restarts: {e}. Initiating emergency shutdown.")
                    await _safe_notify_critical(error_msg)
                    set_emergency_exit_code(2)
                    shutdown_event.set()
                    break
                else:
                    warn_msg = f"[PERINGATAN] <b>[DEGRADED] Auxiliary subsystem {name} hit max restarts ({max_restarts}x)</b>\nError: {e}\nSubsystem diisolasi (cooldown 300s)."
                    logger.warning(f"[DEGRADED] Auxiliary subsystem {name} exceeded max restarts. Isolating error without shutting down: {e}")
                    await _safe_notify_warning(warn_msg)
                    restarts = 0
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=300.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

            is_long_retry = any(lre in error_str for lre in LONG_RETRY_ERRORS)
            delay = min(base_delay * (2 ** (restarts - 1)), max_delay)
            if is_long_retry:
                delay = max(delay, 60.0)
                logger.warning(f"{name} hit rate limit / timeout, enforcing longer delay.")

            logger.error(f"{name} failed with error: {e}. Restarting {restarts}/{max_restarts} in {delay}s...")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass


@dataclass
class TaskDefinition:
    name: str
    runner: Callable[..., Coroutine]
    task_id: str
    is_core: bool = False
    max_restarts: int = 5
    base_delay: float = 10.0
    max_delay: float = 300.0


_global_task_registry: Optional["TaskRegistry"] = None


class TaskRegistry:
    """Registry and orchestrator for background tasks."""

    def __init__(self, shutdown_event: asyncio.Event):
        global _global_task_registry
        self.shutdown_event = shutdown_event
        self._tasks: Dict[str, TaskDefinition] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}
        _global_task_registry = self

    def register(
        self,
        name: str,
        runner: Callable[..., Coroutine],
        task_id: Optional[str] = None,
        is_core: Optional[bool] = None,
        max_restarts: int = 5,
        base_delay: float = 10.0,
        max_delay: float = 300.0,
    ) -> TaskDefinition:
        tid = task_id or name.lower().replace(" ", "_")
        core_flag = is_core if is_core is not None else (name in CORE_TRADING_TASKS)
        defn = TaskDefinition(
            name=name,
            runner=runner,
            task_id=tid,
            is_core=core_flag,
            max_restarts=max_restarts,
            base_delay=base_delay,
            max_delay=max_delay,
        )
        self._tasks[defn.name] = defn
        return defn

    register_task = register

    def get_all(self) -> List[TaskDefinition]:
        return list(self._tasks.values())

    def get_core_tasks(self) -> List[TaskDefinition]:
        return [t for t in self._tasks.values() if t.is_core]

    def create_asyncio_task(self, defn: TaskDefinition) -> asyncio.Task:
        task = asyncio.create_task(
            _run_with_restart(
                defn.name,
                defn.runner,
                self.shutdown_event,
                max_restarts=defn.max_restarts,
                base_delay=defn.base_delay,
                max_delay=defn.max_delay,
            ),
            name=defn.task_id,
        )
        self._active_tasks[defn.name] = task
        return task

    def get_task_status_table(self) -> List[Dict[str, Any]]:
        """Returns live execution status table of all registered background tasks."""
        rows = []
        for name, defn in self._tasks.items():
            t_handle = self._active_tasks.get(name)
            is_alive = False
            state_str = "REGISTERED"
            if t_handle is not None:
                if t_handle.cancelled():
                    state_str = "CANCELLED"
                elif t_handle.done():
                    exc = t_handle.exception() if not t_handle.cancelled() else None
                    state_str = f"ERROR: {exc}" if exc else "COMPLETED"
                else:
                    is_alive = True
                    state_str = "RUNNING"
            rows.append({
                "name": name,
                "task_id": defn.task_id,
                "is_core": defn.is_core,
                "is_alive": is_alive,
                "status": state_str,
                "max_restarts": defn.max_restarts,
            })
        return rows

    @classmethod
    def get_global_instance(cls) -> Optional["TaskRegistry"]:
        return _global_task_registry

    @classmethod
    def get_formatted_status_table(cls, registry: Optional["TaskRegistry"] = None) -> str:
        inst = registry or _global_task_registry
        if not inst or not inst._tasks:
            return "[INFO] *Background Tasks:* Belum ada worker aktif yang terdaftar di TaskRegistry."

        rows = inst.get_task_status_table()
        lines = [f" *STATUS BACKGROUND TASKS ({len(rows)} Registered)*\n"]
        for r in rows:
            st_icon = "[AKTIF]" if r["is_alive"] else ("[NONAKTIF]" if r["status"] == "REGISTERED" else "[KRITIS]")
            core_badge = " `[CORE]`" if r["is_core"] else ""
            lines.append(f"{st_icon} *{r['name']}*{core_badge}\n  Status: `{r['status']}` | Max Restarts: `{r['max_restarts']}`")
        return "\n".join(lines)

