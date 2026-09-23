# ==============================================================================
# File: scheduler/task_plugin.py
# ==============================================================================

"""
Task and Scheduler Plugin Interfaces for Monika Trading Harness.
Provides standardized TaskPlugin ABC, TriggerType, TaskHealth, and
LegacySchedulerWrapper for 100% backward-compatible modular background tasks.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from harness.contract import TradingPlugin, PluginMetadata, PluginCategory, PluginOrigin
from utils.infra.container import ServiceContainer
from agent.task_registry import TaskRegistry, TaskDefinition

logger = logging.getLogger("TradingAgent.Scheduler.TaskPlugin")


class TriggerType(str, Enum):
    INTERVAL = "interval"
    CRON = "cron"
    REACTIVE = "reactive"
    MANUAL = "manual"


class TaskHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class TaskHealth:
    status: TaskHealthStatus = TaskHealthStatus.HEALTHY
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    execution_count: int = 0


class TaskPlugin(TradingPlugin, ABC):
    """
    Base contract for all background schedulers and asynchronous daemon tasks.
    Enables plug-and-play addition or disabling of background tasks via configuration.
    """
    trigger_type: TriggerType = TriggerType.INTERVAL
    interval_seconds: float = 60.0
    is_core: bool = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.health: TaskHealth = TaskHealth()
        self._running: bool = False
        self._task_stop_event: asyncio.Event = asyncio.Event()

    @abstractmethod
    async def run_step(self, container: ServiceContainer) -> None:
        """Execute a single step/cycle of the scheduled task."""
        pass

    async def _loop_runner(self, container: ServiceContainer) -> None:
        """Continuous execution loop with error handling and health updates."""
        self._running = True
        self._task_stop_event.clear()
        
        while self._running and not self._task_stop_event.is_set():
            try:
                self.health.last_run = datetime.now(timezone.utc)
                await self.run_step(container)
                self.health.execution_count += 1
                self.health.status = TaskHealthStatus.HEALTHY
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.health.error_count += 1
                self.health.last_error = str(e)
                self.health.status = TaskHealthStatus.DEGRADED if self.health.error_count < 5 else TaskHealthStatus.FAILED
                logger.error(f"TaskPlugin [{self.metadata.id}] step execution failed: {e}", exc_info=True)

            if self.trigger_type == TriggerType.INTERVAL:
                try:
                    await asyncio.wait_for(self._task_stop_event.wait(), timeout=self.interval_seconds)
                except asyncio.TimeoutError:
                    pass
            else:
                # For reactive or manual triggers, wait for explicit signal
                await self._task_stop_event.wait()
                break

    async def on_start(self, container: ServiceContainer, task_registry: TaskRegistry) -> None:
        """Register the background runner with TaskRegistry."""
        if not self.is_enabled:
            logger.info(f"TaskPlugin [{self.metadata.id}] is disabled — skipping startup.")
            return

        async def runner():
            await self._loop_runner(container)

        task_registry.register(
            name=self.metadata.name,
            runner=runner,
            task_id=self.metadata.id,
            is_core=self.is_core,
        )
        self.status = "RUNNING"
        logger.info(f"TaskPlugin [{self.metadata.id}] registered with TaskRegistry.")

    async def on_stop(self) -> None:
        """Signal the task to stop cleanly."""
        self._running = False
        self._task_stop_event.set()
        self.status = "STOPPED"
        logger.info(f"TaskPlugin [{self.metadata.id}] stopped.")

    def get_health(self) -> TaskHealth:
        """Return the current health metrics of this task."""
        return self.health


class LegacySchedulerWrapper(TaskPlugin):
    """
    Adapter enabling existing monolithic schedulers to operate as modular TaskPlugins
    without requiring any modifications to their internal business logic.
    """

    def __init__(
        self,
        task_id: str,
        name: str,
        target_instance: Any,
        interval_seconds: float = 60.0,
        is_core: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config)
        self.metadata = PluginMetadata(
            id=task_id,
            name=name,
            category=PluginCategory.SCHEDULER,
            origin=PluginOrigin.BUILTIN,
            is_core=is_core,
        )
        self.target = target_instance
        self.interval_seconds = interval_seconds
        self.is_core = is_core

    async def run_step(self, container: ServiceContainer) -> None:
        """Delegate single execution step to wrapped scheduler instance."""
        if hasattr(self.target, "run_once"):
            res = self.target.run_once()
            if asyncio.iscoroutine(res):
                await res
        elif hasattr(self.target, "check"):
            res = self.target.check()
            if asyncio.iscoroutine(res):
                await res
        elif hasattr(self.target, "sync_now"):
            res = self.target.sync_now()
            if asyncio.iscoroutine(res):
                await res
        elif hasattr(self.target, "poll_once"):
            res = self.target.poll_once()
            if asyncio.iscoroutine(res):
                await res
        elif hasattr(self.target, "run_step"):
            res = self.target.run_step(container)
            if asyncio.iscoroutine(res):
                await res
        else:
            logger.debug(f"LegacySchedulerWrapper [{self.metadata.id}] has no single-step method.")

    async def on_start(self, container: ServiceContainer, task_registry: TaskRegistry) -> None:
        """If target has its own native .start() loop, delegate directly to task_registry."""
        if not self.is_enabled:
            logger.info(f"LegacyScheduler [{self.metadata.id}] disabled — skipping.")
            return

        if hasattr(self.target, "start") and callable(self.target.start):
            start_fn = self.target.start
            # Register native target.start directly with TaskRegistry
            task_registry.register(
                name=self.metadata.name,
                runner=start_fn,
                task_id=self.metadata.id,
                is_core=self.is_core,
            )
            self.status = "RUNNING"
            logger.info(f"LegacyScheduler [{self.metadata.id}] registered native start loop.")
        else:
            # Fall back to periodic run_step loop
            await super().on_start(container, task_registry)

    async def on_stop(self) -> None:
        """Stop wrapped legacy scheduler."""
        if hasattr(self.target, "stop") and callable(self.target.stop):
            res = self.target.stop()
            if asyncio.iscoroutine(res):
                await res
        elif hasattr(self.target, "aclose") and callable(self.target.aclose):
            res = self.target.aclose()
            if asyncio.iscoroutine(res):
                await res
        await super().on_stop()
