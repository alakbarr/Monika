# ==============================================================================
# File: tests/scheduler/test_task_plugin_lifecycle.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from harness.contract import PluginMetadata, PluginCategory, PluginOrigin
from utils.infra.container import ServiceContainer
from agent.task_registry import TaskRegistry
from scheduler.task_plugin import (
    TaskPlugin,
    LegacySchedulerWrapper,
    TriggerType,
    TaskHealthStatus,
)


class DummyCounterTask(TaskPlugin):
    def __init__(self):
        super().__init__()
        self.metadata = PluginMetadata(
            id="dummy_counter",
            name="Dummy Counter",
            category=PluginCategory.SCHEDULER,
            origin=PluginOrigin.BUILTIN,
        )
        self.counter = 0
        self.interval_seconds = 0.01

    async def run_step(self, container: ServiceContainer) -> None:
        self.counter += 1


@pytest.mark.asyncio
async def test_task_plugin_custom_step():
    container = ServiceContainer()
    shutdown_event = asyncio.Event()
    registry = TaskRegistry(shutdown_event)

    plugin = DummyCounterTask()
    assert plugin.status == "INITIALIZED"

    await plugin.on_start(container, registry)
    assert plugin.status == "RUNNING"

    all_tasks = registry.get_all()
    assert len(all_tasks) == 1
    task_defn = all_tasks[0]
    assert task_defn.task_id == "dummy_counter"

    # Run the runner in background for a brief moment
    runner_task = asyncio.create_task(task_defn.runner())
    await asyncio.sleep(0.05)

    assert plugin.counter > 0
    health = plugin.get_health()
    assert health.status == TaskHealthStatus.HEALTHY
    assert health.execution_count > 0
    assert health.error_count == 0

    await plugin.on_stop()
    assert plugin.status == "STOPPED"
    runner_task.cancel()
    try:
        await runner_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_legacy_scheduler_wrapper_native_start():
    container = ServiceContainer()
    shutdown_event = asyncio.Event()
    registry = TaskRegistry(shutdown_event)

    legacy_mock = MagicMock()
    legacy_mock.start = AsyncMock()
    legacy_mock.stop = AsyncMock()

    wrapper = LegacySchedulerWrapper(
        task_id="mock_guardian",
        name="Mock Guardian",
        target_instance=legacy_mock,
        is_core=True,
    )

    await wrapper.on_start(container, registry)
    assert wrapper.status == "RUNNING"

    tasks = registry.get_all()
    assert len(tasks) == 1
    assert tasks[0].task_id == "mock_guardian"
    assert tasks[0].is_core is True

    await wrapper.on_stop()
    assert wrapper.status == "STOPPED"
    legacy_mock.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_scheduler_wrapper_periodic_step():
    container = ServiceContainer()
    shutdown_event = asyncio.Event()
    registry = TaskRegistry(shutdown_event)

    legacy_target = MagicMock()
    # No start() method, only run_once()
    del legacy_target.start
    legacy_target.run_once = AsyncMock(return_value={"status": "ok"})
    legacy_target.stop = MagicMock()

    wrapper = LegacySchedulerWrapper(
        task_id="mock_step_worker",
        name="Mock Step Worker",
        target_instance=legacy_target,
        interval_seconds=0.01,
    )

    await wrapper.on_start(container, registry)
    task_defn = registry.get_all()[0]

    runner_task = asyncio.create_task(task_defn.runner())
    await asyncio.sleep(0.04)

    assert legacy_target.run_once.call_count >= 1
    health = wrapper.get_health()
    assert health.status == TaskHealthStatus.HEALTHY

    await wrapper.on_stop()
    legacy_target.stop.assert_called_once()
    runner_task.cancel()
    try:
        await runner_task
    except asyncio.CancelledError:
        pass
