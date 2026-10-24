"""
File: src/monika/application/agent/task_registry.py
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


class EmergencyExitCoordinator:
    """Coordinates fail-closed emergency exit codes across daemon modules."""

    exit_code: Optional[int] = None

    @classmethod
    def get_code(cls) -> Optional[int]:
        return cls.exit_code

    @classmethod
    def set_code(cls, code: Optional[int]) -> None:
        cls.exit_code = code
        import sys

        for mod_name in ("main", "__main__", "monika.application.main", "monika.application.orchestrator"):
            main_mod = sys.modules.get(mod_name)
            if main_mod is not None:
                try:
                    setattr(main_mod, "_EMERGENCY_EXIT_CODE", code)
                except Exception:
                    pass

    @classmethod
    def reset(cls) -> None:
        cls.exit_code = None


def get_emergency_exit_code() -> Optional[int]:
    return EmergencyExitCoordinator.get_code()


def set_emergency_exit_code(code: Optional[int]) -> None:
    EmergencyExitCoordinator.set_code(code)


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
        from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

        notifier = AgentNotifier()
        await asyncio.wait_for(notifier.send_warning(msg), timeout=3.0)
    except Exception as notify_err:
        logger.debug(f"Gagal mengirim warning Telegram: {notify_err}")


async def _safe_notify_critical(msg: str) -> None:
    try:
        from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

        notifier = AgentNotifier()
        await asyncio.wait_for(notifier.send_critical(msg), timeout=3.0)
    except Exception as notify_err:
        logger.error(f"Gagal mengirim notifikasi fatal Telegram: {notify_err}")


PERMANENT_ERRORS = [
    "AuthenticationError",
    "invalid_api_key",
    "API key",
    "Invalid model",
    "model_not_found",
    "DATABASE_URL",
    "could not connect to database",
    'relation ".*" does not exist',
    'column ".*" does not exist',
    "No section: ",
    "No option ",
    "settings.yaml",
    "CERTIFICATE_VERIFY_FAILED",
    "billing_hard_limit_reached",
    "quota_exceeded_permanently",
]

LONG_RETRY_ERRORS = [
    "Connection reset by peer",
    "SSL:",
    "timeout",
    "overloaded",
    "529",
    "503",
    "rate_limit",
]


def _extract_task_owner(func: Any) -> Optional[Any]:
    """Extract owner object from bound method, partial, wrapper, attribute, or closure."""
    if func is None:
        return None
    # 1. Bound method
    owner = getattr(func, "__self__", None)
    if owner is not None:
        return owner
    # 2. Explicit owner attribute
    if hasattr(func, "owner"):
        return getattr(func, "owner")
    # 3. functools.partial
    if hasattr(func, "func"):
        owner = _extract_task_owner(getattr(func, "func"))
        if owner is not None:
            return owner
    # 4. Decorator wrapper
    if hasattr(func, "__wrapped__"):
        owner = _extract_task_owner(getattr(func, "__wrapped__"))
        if owner is not None:
            return owner
    # 5. Closure cells (e.g. async def runner() enclosing self)
    if hasattr(func, "__closure__") and func.__closure__:
        for cell in func.__closure__:
            try:
                val = cell.cell_contents
                if hasattr(val, "_running") or hasattr(val, "is_running") or hasattr(val, "status"):
                    return val
            except Exception:
                continue
    return None


async def _run_with_restart(
    name: str,
    coro_factory,
    shutdown_event: asyncio.Event,
    is_finite: bool = False,
    max_restarts: int = 5,
    base_delay: float = 10.0,
    max_delay: float = 300.0,
):
    """
    Supervises a background task with bulkhead isolation, exponential backoff,
    and fail-closed emergency shutdown for core tasks.
    """
    restarts = 0
    last_success_time = _time.monotonic()

    while not shutdown_event.is_set():
        try:
            await coro_factory()
            if shutdown_event.is_set():
                break

            if is_finite or getattr(coro_factory, "is_finite", False):
                logger.info(f"{name} completed successfully (finite task).")
                break

            self_obj = _extract_task_owner(coro_factory)
            if self_obj is not None:
                if hasattr(self_obj, "_running") and not self_obj._running:
                    logger.info(f"{name} stopped.")
                    break
                if hasattr(self_obj, "status") and str(getattr(self_obj, "status", "")).upper() in (
                    "STOPPED",
                    "DONE",
                    "COMPLETED",
                ):
                    logger.info(f"{name} stopped (status={self_obj.status}).")
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
                    logger.critical(
                        f"[EMERGENCY] Core trading task {name} exited cleanly {max_restarts} times unexpectedly. Initiating emergency shutdown."
                    )
                    set_emergency_exit_code(2)
                    shutdown_event.set()
                    break
                else:
                    logger.warning(
                        f"[DEGRADED] Auxiliary subsystem {name} exited {max_restarts} times. Isolating with 300s cooldown."
                    )
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
                    logger.critical(
                        f"[EMERGENCY] Core trading subsystem {name} failed permanently: {e}. Initiating emergency shutdown."
                    )
                    await _safe_notify_critical(error_msg)
                    set_emergency_exit_code(2)
                    shutdown_event.set()
                    break
                else:
                    warn_msg = f"[PERINGATAN] <b>[DEGRADED] Auxiliary subsystem {name} failed (permanent error)</b>\nError: {e}\nSubsystem auxiliary diisolasi (cooldown 300s)."
                    logger.warning(
                        f"[DEGRADED] Auxiliary subsystem {name} failed. Isolating error without shutting down: {e}"
                    )
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
                    logger.critical(
                        f"[EMERGENCY] Core trading subsystem {name} exceeded max restarts: {e}. Initiating emergency shutdown."
                    )
                    await _safe_notify_critical(error_msg)
                    set_emergency_exit_code(2)
                    shutdown_event.set()
                    break
                else:
                    warn_msg = f"[PERINGATAN] <b>[DEGRADED] Auxiliary subsystem {name} hit max restarts ({max_restarts}x)</b>\nError: {e}\nSubsystem diisolasi (cooldown 300s)."
                    logger.warning(
                        f"[DEGRADED] Auxiliary subsystem {name} exceeded max restarts. Isolating error without shutting down: {e}"
                    )
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
    is_finite: bool = False
    max_restarts: int = 5
    base_delay: float = 10.0
    max_delay: float = 300.0


class TaskRegistry:
    """Registry and orchestrator for background tasks."""

    _instance: Optional["TaskRegistry"] = None

    def __init__(self, shutdown_event: asyncio.Event):
        self.shutdown_event = shutdown_event
        self._tasks: Dict[str, TaskDefinition] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}
        TaskRegistry._instance = self

    @classmethod
    def get_instance(cls, shutdown_event: Optional[asyncio.Event] = None) -> "TaskRegistry":
        if cls._instance is None:
            ev = shutdown_event or asyncio.Event()
            cls._instance = cls(shutdown_event=ev)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def register(
        self,
        name: str,
        runner: Callable[..., Coroutine],
        task_id: Optional[str] = None,
        is_core: Optional[bool] = None,
        is_finite: bool = False,
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
            is_finite=is_finite,
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
                is_finite=defn.is_finite,
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
            rows.append(
                {
                    "name": name,
                    "task_id": defn.task_id,
                    "is_core": defn.is_core,
                    "is_alive": is_alive,
                    "status": state_str,
                    "max_restarts": defn.max_restarts,
                }
            )
        return rows

    @classmethod
    def get_global_instance(cls) -> Optional["TaskRegistry"]:
        return cls._instance

    @classmethod
    def get_formatted_status_table(cls, registry: Optional["TaskRegistry"] = None) -> str:
        inst = registry or cls._instance
        if not inst or not inst._tasks:
            return "[INFO] *Background Tasks:* Belum ada worker aktif yang terdaftar di TaskRegistry."

        rows = inst.get_task_status_table()
        lines = [f" *STATUS BACKGROUND TASKS ({len(rows)} Registered)*\n"]
        for r in rows:
            st_icon = "[AKTIF]" if r["is_alive"] else ("[NONAKTIF]" if r["status"] == "REGISTERED" else "[KRITIS]")
            core_badge = " `[CORE]`" if r["is_core"] else ""
            lines.append(
                f"{st_icon} *{r['name']}*{core_badge}\n  Status: `{r['status']}` | Max Restarts: `{r['max_restarts']}`"
            )
        return "\n".join(lines)
