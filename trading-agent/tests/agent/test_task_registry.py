# ==============================================================================
# File: tests/agent/test_task_registry.py
# ==============================================================================

import os
import sys
import types
import pytest
from agent.task_registry import (
    CORE_TRADING_TASKS,
    TaskDefinition,
    TaskRegistry,
    get_emergency_exit_code,
    set_emergency_exit_code,
    mark_clean_shutdown,
    CLEAN_SHUTDOWN_FLAG,
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
    if os.path.exists(CLEAN_SHUTDOWN_FLAG):
        os.remove(CLEAN_SHUTDOWN_FLAG)

    mark_clean_shutdown()
    assert os.path.exists(CLEAN_SHUTDOWN_FLAG)

    with open(CLEAN_SHUTDOWN_FLAG, "r", encoding="utf-8") as f:
        content = f.read().strip()
        assert len(content) > 0
