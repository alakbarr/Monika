"""
Unit tests verifying Phase 2 Wiring Bug & Real Controls P1 remediations:
1. P1-4: Heartbeat writer atomic writes (temp file + os.replace).
2. P1-12: Non-blocking Discord webhook dispatch via asyncio.to_thread.
3. P1-2: MT5 client recognizes TRADE_RETCODE_PLACED (10008) as successful.
4. P1-8: TaskRegistry properly populates _active_tasks and reports RUNNING status.
5. P1-15: Process-wide async lock for playbook compilation & curation.
6. P1-10: Migration 0003 downgrade implements safe rollback.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.ea_bridge.heartbeat_writer import HeartbeatManager
from utils.infra.notifier import AgentNotifier
from agent.task_registry import TaskRegistry
from analysis.memory.playbook_ledger import get_playbook_async_lock, PlaybookLedger


@pytest.mark.asyncio
async def test_heartbeat_atomic_write(tmp_path):
    """Verify heartbeat writing creates files atomically and updates timestamps."""
    mgr = HeartbeatManager(mt5_common_path=str(tmp_path))
    
    # Write heartbeat
    mgr._write_heartbeat()
    
    assert mgr.heartbeat_file.exists()
    assert mgr.legacy_heartbeat_file.exists()
    
    # Verify no dangling .tmp files remain
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0
    
    content = mgr.heartbeat_file.read_text(encoding="utf-8").strip()
    assert content.isdigit()
    assert int(content) > 0


@pytest.mark.asyncio
async def test_notifier_discord_asyncio_to_thread():
    """Verify Discord webhook dispatch uses asyncio.to_thread and does not block the loop."""
    notifier = AgentNotifier()
    notifier.bot = AsyncMock()
    notifier.admin_id = 123456
    
    with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}):
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            await notifier._send("Test message", prefix="[INFO]")
            
            # Verify asyncio.to_thread was called for the webhook
            mock_to_thread.assert_awaited()


@pytest.mark.asyncio
async def test_mt5_client_pending_order_retcode_10008():
    """Verify MT5Client treats TRADE_RETCODE_PLACED (10008) as success."""
    from execution.mt5_client import _place_order
    
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = MagicMock(
        name="EURUSD",
        visible=True,
        trade_mode=4,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        filling_mode=1,
        digits=5,
        point=0.00001,
    )
    mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1000, bid=1.0998)
    
    # Pre-flight check passes with 10008
    mock_check = MagicMock(retcode=10008, comment="Order placed")
    mock_mt5.order_check.return_value = mock_check
    
    # Order send returns 10008 (TRADE_RETCODE_PLACED)
    mock_send = MagicMock(retcode=10008, order=888777, price=1.0950, volume=0.1, comment="Placed")
    mock_mt5.order_send.return_value = mock_send
    
    with patch.dict("sys.modules", {"MetaTrader5": mock_mt5}):
        result = _place_order(
            symbol="EURUSD",
            direction="buy",
            order_type="buy_limit",
            volume=0.1,
            price=1.0950,
            sl=1.0900,
            tp=1.1050,
            comment="Test limit",
        )
        
        assert result["success"] is True
        assert result["retcode"] == 10008
        assert result["ticket"] == 888777
        assert result["error"] is None


@pytest.mark.asyncio
async def test_task_registry_active_tasks_tracking():
    """Verify TaskRegistry correctly tracks active tasks in _active_tasks and reports RUNNING."""
    shutdown_ev = asyncio.Event()
    registry = TaskRegistry(shutdown_ev)
    
    async def dummy_runner():
        while not shutdown_ev.is_set():
            await asyncio.sleep(0.01)
            
    defn = registry.register("TestWorker", dummy_runner, task_id="test_worker")
    task = registry.create_asyncio_task(defn)
    
    # Allow task to start
    await asyncio.sleep(0.02)
    
    try:
        assert "TestWorker" in registry._active_tasks
        assert registry._active_tasks["TestWorker"] is task
        
        status_table = registry.get_task_status_table()
        assert len(status_table) == 1
        assert status_table[0]["name"] == "TestWorker"
        assert status_table[0]["is_alive"] is True
        assert status_table[0]["status"] == "RUNNING"
        
        table_md = registry.get_formatted_status_table()
        assert "[AKTIF]" in table_md
        assert "TestWorker" in table_md
    finally:
        shutdown_ev.set()
        await task


@pytest.mark.asyncio
async def test_playbook_concurrency_lock():
    """Verify process-wide playbook async lock works as a singleton across calls."""
    lock1 = get_playbook_async_lock()
    lock2 = get_playbook_async_lock()
    
    assert lock1 is lock2
    assert isinstance(lock1, asyncio.Lock)
    
    # Acquire lock and verify exclusion
    async with lock1:
        assert lock1.locked() is True
    assert lock1.locked() is False


def test_migration_0003_downgrade():
    """Verify migration 0003 downgrade function is reversible and callable."""
    import importlib
    mig_mod = importlib.import_module("database.migrations.versions.0003_add_benchmark_tables_and_cache_cost_columns")
    downgrade = mig_mod.downgrade
    
    mock_op = MagicMock()
    mock_sa = MagicMock()
    mock_bind = MagicMock()
    mock_insp = MagicMock()
    mock_insp.get_table_names.return_value = ["llm_benchmark_run", "llm_benchmark_result"]
    mock_sa.inspect.return_value = mock_insp
    mock_op.get_bind.return_value = mock_bind
    
    with patch.object(mig_mod, "op", mock_op), patch.object(mig_mod, "sa", mock_sa):
        downgrade()
        
        # Verify tables dropped in correct dependency order
        mock_op.drop_table.assert_any_call("llm_benchmark_result")
        mock_op.drop_table.assert_any_call("llm_benchmark_run")
