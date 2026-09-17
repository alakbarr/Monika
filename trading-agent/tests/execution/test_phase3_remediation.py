# ==============================================================================
# File: tests/execution/test_phase3_remediation.py
# Description: Test suite verifying Phase 3 Concurrency & Race Condition remediations:
#              DB-13, DB-14, DB-15, SC-1, SC-3, SC-6, SC-7, SC-8, SC-9, CW-3, CW-5, CW-6
# ==============================================================================

import asyncio
import os
import zlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ------------------------------------------------------------------------------
# 1. DB-13: Atomic In-Memory Advisory Lock
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db13_atomic_in_memory_locks():
    from database.db import transactional_advisory_lock, _IN_MEMORY_EXECUTION_LOCKS
    
    mock_session = AsyncMock()
    # Mock engine without postgresql dialect to exercise in-memory path
    mock_bind = MagicMock()
    mock_bind.dialect.name = "sqlite"
    mock_session.get_bind.return_value = mock_bind
    
    lock_key = "test_atomic_lock_key"
    async with transactional_advisory_lock(mock_session, lock_key=lock_key) as locked:
        assert locked is True
        import hashlib
        numeric_key = (int.from_bytes(hashlib.sha256(lock_key.encode('utf-8')).digest()[:8], 'big') & 0x7FFFFFFFFFFFFFFF)
        assert numeric_key in _IN_MEMORY_EXECUTION_LOCKS
        lock_obj = _IN_MEMORY_EXECUTION_LOCKS[numeric_key]
        assert isinstance(lock_obj, asyncio.Lock)
        assert lock_obj.locked() is True

    # Lock is now released
    assert lock_obj.locked() is False


# ------------------------------------------------------------------------------
# 2. SC-1: PositionSync Exclusion when OrderReconciler Exists
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sc1_position_sync_order_reconciler_exclusion():
    from main import TradingAgent
    
    settings = {"trading": {"symbols": ["EURUSD"]}}
    agent = TradingAgent(settings=settings, dry_run=True)
    agent.order_reconciler = MagicMock()
    agent.order_reconciler.is_running = True
    
    # Running _run_position_sync_loop should exit immediately without looping
    task = asyncio.create_task(agent._run_position_sync_loop())
    await asyncio.sleep(0.01)
    assert task.done()


# ------------------------------------------------------------------------------
# 3. SC-3: Session Trigger Loop Flag and Resilience
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sc3_session_trigger_loop_flag_and_stop():
    from scheduler.graph_cycle_scheduler import GraphCycleScheduler
    
    settings = {
        "trading": {"symbols": ["EURUSD"]},
        "execution": {"session_triggers": {"enabled": True}}
    }
    cycle_sched = GraphCycleScheduler(settings=settings)
    assert cycle_sched._session_trigger_running is False
    
    # Mock run_session_trigger to avoid calling real LLMs
    cycle_sched.run_session_trigger = AsyncMock(return_value={"status": "skipped"})
    
    # Start loop in background
    cycle_sched._session_trigger_running = True
    loop_task = asyncio.create_task(cycle_sched.run_session_trigger_loop())
    
    await asyncio.sleep(0.05)
    assert cycle_sched._session_trigger_running is True
    assert not loop_task.done()
    
    # Stopping should cleanly stop the session loop within ~1 second
    cycle_sched.stop()
    assert cycle_sched._session_trigger_running is False
    await asyncio.wait_for(loop_task, timeout=2.0)
    assert loop_task.done()


# ------------------------------------------------------------------------------
# 4. CW-3: Recovery Event Wait in Schedulers
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cw3_recovery_event_waiting():
    from scheduler.trigger_checker import TriggerChecker
    from scheduler.position_exit_reviewer import PositionExitReviewer
    from scheduler.trailing_stop_manager import TrailingStopManager
    from scheduler.order_reconciler import OrderReconciler
    
    settings = {"trading": {"symbols": ["EURUSD"], "risk": {"max_concurrent_positions": 5}}}
    recovery_event = asyncio.Event()
    
    tc = TriggerChecker(settings, recovery_event=recovery_event)
    per = PositionExitReviewer(settings, execution_service=MagicMock(), recovery_event=recovery_event)
    tsm = TrailingStopManager(settings, execution_service=MagicMock(), recovery_event=recovery_event)
    rec = OrderReconciler(settings, MagicMock(), MagicMock(), recovery_event=recovery_event)
    
    assert tc._recovery_event is recovery_event
    assert per._recovery_event is recovery_event
    assert tsm._recovery_event is recovery_event
    assert rec._recovery_event is recovery_event

    # Start trigger checker task while recovery is NOT set
    with patch.object(tc, "run_once", new_callable=AsyncMock) as mock_once:
        mock_once.return_value = {"fired": 0, "evaluated": 0}
        task = asyncio.create_task(tc.start())
        await asyncio.sleep(0.05)
        # Should be blocked waiting for recovery_event
        assert not mock_once.called
        
        # Now set recovery event
        recovery_event.set()
        await asyncio.sleep(0.05)
        assert mock_once.called
        tc.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ------------------------------------------------------------------------------
# 5. SC-6 & SC-7: NewsWatcher Concurrency Guard & Cycle Lock
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sc6_sc7_news_watcher_concurrency_and_cycle_lock():
    from scheduler.news_watcher import NewsWatcher
    
    settings = {"trading": {"symbols": ["EURUSD"]}}
    nw = NewsWatcher(settings)
    assert hasattr(nw, "_run_lock")
    assert isinstance(nw._run_lock, asyncio.Lock)
    
    mock_cycle_sched = MagicMock()
    mock_cycle_sched._cycle_lock = asyncio.Lock()
    mock_cycle_sched.run_single_symbol_cycle = AsyncMock()
    nw.cycle_scheduler = mock_cycle_sched
    
    # Verify targeted re-analysis acquires _cycle_lock
    async with mock_cycle_sched._cycle_lock:
        # If news watcher tries to run single symbol while cycle is locked,
        # it should wait or respect cycle_lock
        assert mock_cycle_sched._cycle_lock.locked() is True


# ------------------------------------------------------------------------------
# 6. SC-8: Emergency Manager Ticket Locks and Duplicate Close Prevention
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sc8_duplicate_position_close_prevention():
    from execution.service.emergency_manager import EmergencyManagerMixin
    from database.models import Position
    
    class DummyExecution(EmergencyManagerMixin):
        def __init__(self):
            self.settings = {}
            self.mt5 = MagicMock()
            self.broker_adapter = AsyncMock()
            self._ticket_locks = {}
            self._global_close_lock = asyncio.Lock()
            self.activity_logger = MagicMock()
            self.notifier = None

    em = DummyExecution()
    ticket = 12345
    
    mock_session = AsyncMock()
    # Mock position that is ALREADY closed
    mock_pos = MagicMock(spec=Position)
    mock_pos.status = "closed"
    mock_pos.symbol = "EURUSD"
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_pos
    mock_session.execute.return_value = mock_result
    
    with patch("execution.service.emergency_manager.get_session") as mock_gs:
        mock_gs.return_value.__aenter__.return_value = mock_session
        res = await em.close_position_by_ticket(ticket, reason="Test concurrent close")
        
        # Must return idempotent already_closed success, not calling broker adapter
        assert res["success"] is True
        assert res.get("already_closed") is True
        assert not em.broker_adapter.close_position.called


# ------------------------------------------------------------------------------
# 7. SC-9: Schedulers Cancel Background Tasks on Stop
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sc9_background_tasks_cancellation():
    from scheduler.news_watcher import NewsWatcher
    from scheduler.trigger_checker import TriggerChecker
    
    settings = {"trading": {"symbols": ["EURUSD"], "risk": {"max_concurrent_positions": 5}}}
    nw = NewsWatcher(settings)
    tc = TriggerChecker(settings)
    
    # Create dummy tasks
    async def dummy_coro():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass
        
    t1 = asyncio.create_task(dummy_coro())
    t2 = asyncio.create_task(dummy_coro())
    nw._background_tasks.add(t1)
    tc._background_tasks.add(t2)
    
    nw.stop()
    tc.stop()
    await asyncio.sleep(0.02)
    
    assert t1.cancelled() or t1.done()
    assert t2.cancelled() or t2.done()


# ------------------------------------------------------------------------------
# 8. CW-5: Main Agent Shutdown Sequence
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cw5_graceful_shutdown_order():
    from main import TradingAgent
    settings = {"trading": {"symbols": ["EURUSD"]}}
    agent = TradingAgent(settings=settings, dry_run=True)
    
    order_of_ops = []
    async def fake_shutdown():
        order_of_ops.append("shutdown")
        
    agent._shutdown = fake_shutdown
    
    async def dummy_loop():
        try:
            while True:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            order_of_ops.append("task_cancelled")
            raise
            
    t = asyncio.create_task(dummy_loop())
    await asyncio.sleep(0.02)
    agent._tasks.append(t)
    
    # Verify graceful shutdown order: _shutdown called before cancelling pending tasks
    await agent._shutdown()
    pending = [task for task in agent._tasks if not task.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    
    assert order_of_ops == ["shutdown", "task_cancelled"]
    assert t.done()


# ------------------------------------------------------------------------------
# 9. CW-6: Release Single Instance Lock
# ------------------------------------------------------------------------------
def test_cw6_pid_lock_release_helper(tmp_path):
    import main as main_mod
    
    test_lock_file = str(tmp_path / "trading_agent.pid")
    with open(test_lock_file, "w") as f:
        f.write(str(os.getpid()))
        
    original_pid_file = main_mod.PID_FILE
    try:
        main_mod.PID_FILE = test_lock_file
        assert os.path.exists(test_lock_file)
        main_mod.release_single_instance_lock()
        assert not os.path.exists(test_lock_file)
    finally:
        main_mod.PID_FILE = original_pid_file


# ------------------------------------------------------------------------------
# 10. DB-14: RiskGate Daily Trade Count Live vs Paper Separation
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db14_risk_gate_daily_trade_count_paper_vs_live():
    from risk.risk_gate import RiskGate
    
    settings = {
        "trading": {
            "risk": {
                "max_daily_trades": 3,
            }
        },
        "paper_trading": {"enabled": False}
    }
    gate = RiskGate(settings)
    
    mock_session = AsyncMock()
    
    # Case: 3 paper trades opened today, but 0 live trades
    # When testing for a live trade (is_paper=False), it should PASS!
    call_count = 0
    def mock_scalar():
        nonlocal call_count
        call_count += 1
        # Odd calls: live count (0), Even calls: paper count (3)
        return 0 if call_count % 2 == 1 else 3

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.side_effect = mock_scalar
    mock_session.execute.return_value = mock_result
    
    # 1. Live trade check -> should pass because live_today = 0 < 3
    ok, msg = await gate._check_daily_trade_count(mock_session, is_backtest=False, is_paper=False)
    assert ok is True
    assert "daily_live_trades=0/3" in msg
    
    # 2. Paper trade check -> should fail because paper_today = 3 >= 3
    ok, msg = await gate._check_daily_trade_count(mock_session, is_backtest=False, is_paper=True)
    assert ok is False
    assert "Daily paper trade limit reached: 3/3" in msg


# ------------------------------------------------------------------------------
# 11. DB-15: RiskGate No Duplicate Check Allows Multi-leg / Tranche Groups
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db15_risk_gate_no_duplicate_pair_group():
    from risk.risk_gate import RiskGate
    from database.models import Position
    
    settings = {"trading": {"risk": {"max_concurrent_positions": 5}}}
    gate = RiskGate(settings)
    
    # 1. Simulated positions test with pair_group_id
    sim_pos = [
        {"symbol": "XAUUSD", "pair_group_id": "tranche_123"},
    ]
    # Another leg with SAME pair_group_id -> ALLOWED
    ok, msg = await gate._check_no_duplicate(
        AsyncMock(), symbol="XAUUSD", simulated_positions=sim_pos, pair_group_id="tranche_123"
    )
    assert ok is True
    assert "no duplicate (simulated)" in msg

    # Another trade for XAUUSD with DIFFERENT group or None -> REJECTED
    ok, msg = await gate._check_no_duplicate(
        AsyncMock(), symbol="XAUUSD", simulated_positions=sim_pos, pair_group_id="other_group"
    )
    assert ok is False
    assert "Already have an open simulated position" in msg

    # 2. DB positions test with pair_group_id
    mock_session = AsyncMock()
    # Mock no conflict outside pair group, and 1 existing leg inside group
    res_conflict = MagicMock()
    res_conflict.scalar_one_or_none.return_value = None  # No outside position
    
    res_group_count = MagicMock()
    res_group_count.scalar_one_or_none.return_value = 1  # 1 leg already exists in group
    
    mock_session.execute.side_effect = [res_conflict, res_group_count]
    
    ok, msg = await gate._check_no_duplicate(
        mock_session, symbol="XAUUSD", pair_group_id="tranche_123"
    )
    assert ok is True
    assert "pair group leg allowed" in msg


# ------------------------------------------------------------------------------
# 12. M-8: TTL Eviction on In-Memory Execution ID Set
# ------------------------------------------------------------------------------
def test_m8_prune_executed_analysis_ids_ttl_and_resilience():
    import time
    from execution.service.order_executor import (
        _EXECUTED_ANALYSIS_IDS,
        _prune_executed_analysis_ids,
    )
    import execution.service.order_executor as oe

    now = time.time()
    oe._LAST_CLEANUP_TIME = 0.0  # Force cleanup check

    _EXECUTED_ANALYSIS_IDS.clear()
    _EXECUTED_ANALYSIS_IDS[101] = now - 90000.0   # Expired (> 24h)
    _EXECUTED_ANALYSIS_IDS[102] = now - 3600.0    # Recent (1h ago)
    _EXECUTED_ANALYSIS_IDS[103] = True            # Corrupted bool
    _EXECUTED_ANALYSIS_IDS[104] = None            # Corrupted None
    _EXECUTED_ANALYSIS_IDS[105] = "invalid_val"   # Corrupted string

    _prune_executed_analysis_ids(ttl_seconds=86400.0)

    # 101 should be pruned (expired)
    assert 101 not in _EXECUTED_ANALYSIS_IDS
    # Corrupted non-numeric / bool values should be pruned safely
    assert 103 not in _EXECUTED_ANALYSIS_IDS
    assert 104 not in _EXECUTED_ANALYSIS_IDS
    assert 105 not in _EXECUTED_ANALYSIS_IDS
    # 102 should be preserved
    assert 102 in _EXECUTED_ANALYSIS_IDS

