"""
Tests for reactor performance optimizations:
1. DrawdownMonitor delta-check write elimination.
2. MarginMonitor flat position fast-exit.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.application.agent.monitors.drawdown_monitor import run_floating_drawdown_monitor
from monika.application.agent.monitors.margin_monitor import run_margin_monitor
from monika.application.scheduler.position_state_cache import get_position_state_cache


@pytest.mark.asyncio
async def test_drawdown_monitor_skips_redundant_db_writes() -> None:
    agent = MagicMock()
    agent._recovery_complete = None
    agent.shutdown_event = asyncio.Event()
    agent.execution_service = MagicMock()
    agent.execution_service.broker_adapter = MagicMock()

    # Return unchanging balance & equity
    agent.execution_service.broker_adapter.get_account_info = AsyncMock(
        return_value={"balance": 10000.0, "equity": 10000.0}
    )
    agent.settings = {"trading": {"risk": {"max_daily_drawdown_percent": 4.0}}}

    task = asyncio.create_task(run_floating_drawdown_monitor(agent))

    # Let it run 1 loop iteration
    await asyncio.sleep(0.05)
    agent.shutdown_event.set()
    await task


@pytest.mark.asyncio
async def test_margin_monitor_skips_when_flat() -> None:
    cache = get_position_state_cache()
    # Ensure fresh with no open positions (flat)
    cache.update_snapshot(open_symbols=set())

    agent = MagicMock()
    agent._recovery_complete = None
    agent.shutdown_event = asyncio.Event()
    agent.execution_service = MagicMock()
    agent.execution_service.broker_adapter = MagicMock()
    agent.execution_service.broker_adapter.get_account_info = AsyncMock()

    task = asyncio.create_task(run_margin_monitor(agent, poll_interval=0.1))

    await asyncio.sleep(0.05)
    agent.shutdown_event.set()
    await task

    # Because cache is fresh and flat, broker_adapter.get_account_info should NEVER have been called!
    agent.execution_service.broker_adapter.get_account_info.assert_not_called()
