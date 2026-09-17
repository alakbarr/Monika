# ==============================================================================
# File: tests/test_bulkhead_isolation.py
# ==============================================================================

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
import main


@pytest.fixture(autouse=True)
def mock_agent_notifier(monkeypatch):
    """Mock AgentNotifier so tests do not make real network requests to Telegram."""
    mock_notifier = MagicMock()
    mock_notifier.send_warning = AsyncMock()
    mock_notifier.send_critical = AsyncMock()
    mock_notifier.send_info = AsyncMock()
    monkeypatch.setattr("utils.infra.notifier.AgentNotifier", lambda: mock_notifier)
    yield mock_notifier


@pytest.mark.asyncio
async def test_core_trading_tasks_membership():
    """Verify that all mission-critical tasks are included in CORE_TRADING_TASKS."""
    expected_core = {
        "MT5Client",
        "PositionGuardian",
        "TrailingStop",
        "TrailingStopManager",
        "FlashCrashDetector",
        "Heartbeat",
        "HeartbeatManager",
        "FloatingDrawdownMonitor",
        "ExecutionService",
    }
    for task_name in expected_core:
        assert task_name in main.CORE_TRADING_TASKS, f"{task_name} missing from CORE_TRADING_TASKS"


@pytest.mark.asyncio
async def test_auxiliary_task_failure_does_not_trigger_emergency_shutdown():
    """Verify that auxiliary tasks that crash permanently NEVER trigger application shutdown."""
    shutdown_event = asyncio.Event()
    main._EMERGENCY_EXIT_CODE = None

    fail_count = 0

    async def crashing_auxiliary_coro():
        nonlocal fail_count
        fail_count += 1
        if fail_count >= 2:
            # End the loop safely for test termination
            shutdown_event.set()
        raise ValueError("AuthenticationError: invalid_api_key auxiliary test")

    # Run crashing auxiliary task with short delay
    task = asyncio.create_task(
        main._run_with_restart(
            name="ScraperLoop",  # Not in CORE_TRADING_TASKS
            coro_factory=crashing_auxiliary_coro,
            shutdown_event=shutdown_event,
            max_restarts=1,
            base_delay=0.01,
            max_delay=0.05,
        )
    )

    # Wait for the task to run
    await asyncio.sleep(0.1)
    shutdown_event.set()
    await asyncio.wait_for(task, timeout=2.0)

    # Emergency exit code must NOT be set to 2
    assert main._EMERGENCY_EXIT_CODE != 2, "Auxiliary task must never set emergency exit code 2"


@pytest.mark.asyncio
async def test_core_task_failure_triggers_emergency_shutdown():
    """Verify that core trading tasks that fail permanently trigger emergency shutdown (exit code 2)."""
    shutdown_event = asyncio.Event()
    main._EMERGENCY_EXIT_CODE = None

    async def crashing_core_coro():
        raise RuntimeError("DATABASE_URL connection refused fatal error")

    task = asyncio.create_task(
        main._run_with_restart(
            name="PositionGuardian",  # IS in CORE_TRADING_TASKS
            coro_factory=crashing_core_coro,
            shutdown_event=shutdown_event,
            max_restarts=1,
            base_delay=0.01,
            max_delay=0.05,
        )
    )

    await asyncio.wait_for(task, timeout=2.0)

    assert shutdown_event.is_set(), "Core task failure MUST trigger shutdown_event.set()"
    assert main._EMERGENCY_EXIT_CODE == 2, "Core task failure MUST set _EMERGENCY_EXIT_CODE to 2"


def test_mark_clean_shutdown_creates_flag(tmp_path):
    """Verify that mark_clean_shutdown creates the clean shutdown flag file."""
    flag_path = os.path.join("data", "clean_shutdown.flag")
    if os.path.exists(flag_path):
        os.remove(flag_path)

    main.mark_clean_shutdown()
    assert os.path.exists(flag_path), "clean_shutdown.flag must exist after mark_clean_shutdown()"

    with open(flag_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert len(content) > 0, "Flag file must contain timestamp"

    # Clean up test artifact
    os.remove(flag_path)
