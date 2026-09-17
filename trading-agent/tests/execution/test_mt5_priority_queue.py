import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from execution.mt5_client import (
    MT5Client,
    PRIORITY_CRITICAL,
    PRIORITY_STANDARD,
    PRIORITY_BACKGROUND,
)


@pytest.mark.asyncio
async def test_mt5_priority_queue_preemption():
    """Verify that Critical (0) jumps ahead of Standard (5) and Background (10)."""
    client = MT5Client()
    execution_order = []

    def blocker_task():
        time.sleep(0.08)
        execution_order.append("blocker")
        return "blocker_done"

    def bg_task():
        execution_order.append("background_10")
        return "bg_done"

    def std_task():
        execution_order.append("standard_5")
        return "std_done"

    def crit_task():
        execution_order.append("critical_0")
        return "crit_done"

    # Start blocker to occupy single-thread worker
    t_block = asyncio.create_task(client._run(blocker_task, priority=PRIORITY_BACKGROUND))
    await asyncio.sleep(0.01)

    # While worker is blocked, enqueue background (10), standard (5), critical (0)
    t_bg = asyncio.create_task(client._run(bg_task, priority=PRIORITY_BACKGROUND))
    t_std = asyncio.create_task(client._run(std_task, priority=PRIORITY_STANDARD))
    t_crit = asyncio.create_task(client._run(crit_task, priority=PRIORITY_CRITICAL))

    await asyncio.gather(t_block, t_bg, t_std, t_crit)

    # Critical (0) should execute first, then Standard (5), then Background (10)
    assert execution_order == ["blocker", "critical_0", "standard_5", "background_10"]


@pytest.mark.asyncio
async def test_mt5_disconnect_drains_pending_futures():
    """Verify that calling disconnect() rejects all pending tasks instead of hanging forever."""
    client = MT5Client()

    def slow_blocker():
        time.sleep(0.1)
        return "done"

    def pending_task():
        return "should_not_run"

    # Hold worker
    t_block = asyncio.create_task(client._run(slow_blocker, priority=PRIORITY_BACKGROUND))
    await asyncio.sleep(0.01)

    # Queue pending task
    t_pending = asyncio.create_task(client._run(pending_task, priority=PRIORITY_BACKGROUND))

    # Trigger disconnect while pending_task is in queue
    with patch("execution.mt5_client._disconnect", return_value=None):
        await client.disconnect()
    await t_block

    # Pending task must receive ConnectionError instead of hanging forever
    with pytest.raises(ConnectionError, match="MT5 disconnected"):
        await t_pending


@pytest.mark.asyncio
async def test_mt5_emergency_methods_and_aliases():
    """Verify emergency_close_all, kill_switch, and modify_order aliases and prioritization."""
    client = MT5Client()
    client._connected = True
    client.ensure_connected = AsyncMock(return_value=True)

    # Mock open positions
    mock_pos = [{'ticket': 101, 'symbol': 'EURUSD', 'volume': 0.1}]
    client._run = AsyncMock()

    # Test close_all_positions calls _run with PRIORITY_CRITICAL
    client._run.side_effect = [
        mock_pos,  # for _get_open_positions
        {'success': True}  # for _close_position
    ]
    res = await client.emergency_close_all(comment="EMERGENCY")
    assert res['closed'] == 1
    # Check that _get_open_positions was enqueued with PRIORITY_CRITICAL
    assert client._run.call_args_list[0].kwargs.get('priority') == PRIORITY_CRITICAL

    # Test modify_order alias
    client.modify_position = AsyncMock(return_value={'success': True})
    mod_res = await client.modify_order(ticket=101, sl=1.0800, tp=1.0950)
    assert mod_res['success'] is True
    client.modify_position.assert_called_once_with(ticket=101, sl=1.0800, tp=1.0950)

    # Test kill_switch
    client.close_all_positions = AsyncMock(return_value={'closed': 1, 'failed': 0})
    client.disconnect = AsyncMock()
    ks_res = await client.kill_switch("EMERGENCY")
    assert ks_res['closed'] == 1
    client.close_all_positions.assert_called_once()
    client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_mt5_executor_self_healing_after_shutdown():
    """Verify that _ensure_worker resurrects ThreadPoolExecutor if it was shut down."""
    client = MT5Client()
    # Simulate prior shutdown
    client._executor.shutdown(wait=False)
    assert getattr(client._executor, '_shutdown', False) is True

    # Calling _ensure_worker should create a new live executor
    queue = client._ensure_worker()
    assert queue is not None
    assert getattr(client._executor, '_shutdown', False) is False

    # Clean up
    await client.disconnect()
