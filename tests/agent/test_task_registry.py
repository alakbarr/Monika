# ==============================================================================
# File: tests/agent/test_task_registry.py
# ==============================================================================

import os
import sys
import types
import pytest
from unittest.mock import patch
from monika.application.agent.task_registry import (
    CLEAN_SHUTDOWN_FLAG,
    CORE_TRADING_TASKS,
    EmergencyExitCoordinator,
    TaskDefinition,
    TaskRegistry,
    _run_with_restart,
    get_emergency_exit_code,
    mark_clean_shutdown,
    set_emergency_exit_code,
)


def test_emergency_exit_code_lifecycle():
    # Initial / reset
    set_emergency_exit_code(None)
    assert get_emergency_exit_code() is None

    # Set code
    set_emergency_exit_code(2)
    assert get_emergency_exit_code() == 2

    # Reset
    set_emergency_exit_code(None)
    assert get_emergency_exit_code() is None


def test_emergency_exit_code_sync_with_main_module():
    # Mock a dummy main module in sys.modules
    fake_main = types.ModuleType("main")
    original_main = sys.modules.get("main")
    try:
        sys.modules["main"] = fake_main
        set_emergency_exit_code(42)
        assert getattr(fake_main, "_EMERGENCY_EXIT_CODE") == 42
        assert get_emergency_exit_code() == 42
    finally:
        if original_main is not None:
            sys.modules["main"] = original_main
        else:
            sys.modules.pop("main", None)
        set_emergency_exit_code(None)


def test_task_registry_operations():
    import asyncio

    shutdown_event = asyncio.Event()
    registry = TaskRegistry(shutdown_event)

    async def dummy_task():
        pass

    # Register core task
    defn1 = registry.register(
        name="PositionGuardian",
        runner=dummy_task,
        is_core=True,
        max_restarts=3,
        base_delay=1.0,
        max_delay=10.0,
    )

    # Register auxiliary task
    defn2 = registry.register(
        name="OptionalScraper",
        runner=dummy_task,
        is_core=False,
    )

    assert defn1.name == "PositionGuardian"
    assert defn1.is_core is True
    assert defn2.name == "OptionalScraper"
    assert defn2.is_core is False

    core_tasks = registry.get_core_tasks()
    core_names = [t.name for t in core_tasks]
    assert "PositionGuardian" in core_names
    assert "OptionalScraper" not in core_names

    all_tasks = registry.get_all()
    all_names = [t.name for t in all_tasks]
    assert len(all_tasks) == 2
    assert "PositionGuardian" in all_names
    assert "OptionalScraper" in all_names


def test_core_trading_tasks_presence():
    essential_tasks = {
        "MT5Client",
        "PositionGuardian",
        "TrailingStopManager",
        "ExecutionService",
        "CycleScheduler",
    }
    for task in essential_tasks:
        assert task in CORE_TRADING_TASKS, f"{task} must be in CORE_TRADING_TASKS"


def test_mark_clean_shutdown(tmp_path):
    flag_path = str(tmp_path / "clean_shutdown.flag")
    with patch("monika.application.agent.task_registry.CLEAN_SHUTDOWN_FLAG", flag_path):
        mark_clean_shutdown()
        assert os.path.exists(flag_path)

        with open(flag_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            assert len(content) > 0
    if os.path.exists(CLEAN_SHUTDOWN_FLAG):
        os.remove(CLEAN_SHUTDOWN_FLAG)


@pytest.mark.asyncio
async def test_run_with_restart_transient_db_retries():
    """Verify that 'could not connect to database' is treated as transient and retried."""
    import asyncio

    shutdown_event = asyncio.Event()
    attempts = 0

    async def failing_db_task():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("could not connect to database: connection refused")
        shutdown_event.set()

    with patch("monika.infrastructure.notifications.telegram_notifier.AgentNotifier"):
        await _run_with_restart(
            name="TickStream",
            coro_factory=failing_db_task,
            shutdown_event=shutdown_event,
            max_restarts=5,
            base_delay=0.01,
            max_delay=0.05,
        )

    assert attempts == 3
    assert shutdown_event.is_set()


@pytest.mark.asyncio
async def test_run_with_restart_healthy_uptime_resets_counter():
    """Verify that a task running healthily for >= 300s resets its restart counter."""
    import asyncio
    import time as real_time

    shutdown_event = asyncio.Event()
    real_monotonic = real_time.monotonic
    simulated_offset = 0.0
    attempts = 0

    def mock_monotonic():
        return real_monotonic() + simulated_offset

    async def long_running_task():
        nonlocal attempts, simulated_offset
        attempts += 1
        # Advance simulated time by 310s (exceeds 300s healthy uptime threshold)
        simulated_offset += 310.0
        if attempts <= 4:
            raise RuntimeError("Intermittent transient network error")
        shutdown_event.set()

    with (
        patch("monika.application.agent.task_registry._time.monotonic", side_effect=mock_monotonic),
        patch("monika.infrastructure.notifications.telegram_notifier.AgentNotifier"),
    ):
        await _run_with_restart(
            name="PositionGuardian",
            coro_factory=long_running_task,
            shutdown_event=shutdown_event,
            max_restarts=3,  # With 4 errors, if counter did not reset, it would have aborted at attempt 3!
            base_delay=0.01,
            max_delay=0.05,
        )

    assert attempts == 5
    assert shutdown_event.is_set()
