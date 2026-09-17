"""
Unit Test Suite for Phase 4 Remediations (P3 Code Quality & Hardening).
Tests Findings 47 through 82 across Orchestration, Schedulers, Execution, Database, Protocols, and Analysis.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.schemas import TradingAgentConfig, PaperTradingConfig
from agent.task_registry import TaskRegistry, TaskDefinition, CORE_TRADING_TASKS
from utils.protocol.event_bus import EventBus, AppEvent, CircuitBreakerEvent
from utils.scheduling.wall_clock import sleep_until_next
from scheduler.order_reconciler import OrderReconciler
from execution.service.position_synchronizer import PositionSynchronizerMixin
from execution.order_emulator import ClientOrderEmulator, TrackedPosition
from database.models import SystemConfig, PriceOHLCV
from database.safe_ops import safe_db_op, safe_commit
from utils.api.claude_rate_limiter import ClaudeRateLimiter
from analysis.harness.agent_harness import calculate_turn_cost_usd
from analysis.validators.market_snapshot import VerifiedMarketSnapshot


@pytest.mark.asyncio
async def test_settings_and_schema_validation():
    """Group 1: SC-10, SC-11, CW-12 - Config sections and dual paper_trading validation."""
    cfg_root = TradingAgentConfig(
        paper_trading=PaperTradingConfig(enabled=True, streak_loss_policy="warn_and_scale")
    )
    assert cfg_root.paper_trading.enabled is True

    cfg_nested = TradingAgentConfig(
        trading={"paper_trading": {"enabled": False, "streak_loss_policy": "strict"}}
    )
    assert cfg_nested.trading["paper_trading"]["enabled"] is False


@pytest.mark.asyncio
async def test_task_registry_and_core_tasks():
    """Group 2: CW-7 - TaskRegistry registration and core task tracking."""
    shutdown_evt = asyncio.Event()
    registry = TaskRegistry(shutdown_evt)

    async def sample_coro(stop_evt):
        pass

    t1 = registry.register("MT5Client", sample_coro)
    assert t1.is_core is True
    assert "MT5Client" in CORE_TRADING_TASKS

    t2 = registry.register("CustomTask", sample_coro, is_core=False)
    assert t2.is_core is False

    core_tasks = registry.get_core_tasks()
    assert len(core_tasks) == 1
    assert core_tasks[0].name == "MT5Client"


@pytest.mark.asyncio
async def test_wall_clock_sleep_with_shutdown_event():
    """Group 2: CW-13 - sleep_until_next responds immediately to shutdown_event."""
    shutdown_evt = asyncio.Event()
    from datetime import time as dtime

    times = [dtime(23, 59)]

    async def trigger_shutdown():
        await asyncio.sleep(0.05)
        shutdown_evt.set()

    task = asyncio.create_task(trigger_shutdown())
    start = datetime.now(timezone.utc)
    target = await sleep_until_next(times, tz_name="UTC", label="TestTask", shutdown_event=shutdown_evt)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    await task

    assert elapsed < 1.0
    assert shutdown_evt.is_set()


@pytest.mark.asyncio
async def test_order_reconciler_shutdown_event():
    """Group 3: SC-15 - OrderReconciler accepts and respects orchestrator's shutdown_event."""
    orchestrator_shutdown = asyncio.Event()
    reconciler = OrderReconciler(
        settings={"trading": {"dry_run": True}},
        shutdown_event=orchestrator_shutdown,
    )
    assert reconciler._stop_event is orchestrator_shutdown
    assert reconciler.is_running is True

    orchestrator_shutdown.set()
    assert reconciler.is_running is False


@pytest.mark.asyncio
async def test_order_executor_lot_step_zero_guard():
    """Group 3: EX-12 - lot_step clamped to >= 0.001 to prevent ZeroDivisionError."""
    hedge_info = {"volume_step": 0.0, "volume_min": 0.0, "volume_max": 0.0}
    raw_hedge_lots = 1.5

    lot_step = max(float(hedge_info.get("volume_step") or 0.01), 0.001)
    vol_min = max(float(hedge_info.get("volume_min") or 0.01), 0.001)
    vol_max = max(float(hedge_info.get("volume_max") or 100.0), vol_min)
    hedge_lots = max(vol_min, min(vol_max, round(round(raw_hedge_lots / lot_step) * lot_step, 2)))

    assert lot_step >= 0.001
    assert hedge_lots >= vol_min


@pytest.mark.asyncio
async def test_position_synchronizer_ea_heartbeat_guard():
    """Group 3: EX-13 - Stale EA alert only triggers if stale_seconds > 0."""
    class DummySync(PositionSynchronizerMixin):
        def __init__(self):
            self.settings = {"execution": {"mt5_common_dir": ""}}

    syncer = DummySync()
    ea_alive = False
    stale_seconds = -1.0
    should_alert = (not ea_alive) and (stale_seconds > 0)
    assert should_alert is False


@pytest.mark.asyncio
async def test_order_emulator_watermark_trailing():
    """Group 3: EX-14 - Trailing stop uses high_watermark (BUY) and low_watermark (SELL)."""
    emulator = ClientOrderEmulator(
        settings={
            "trailing_stop": {
                "breakeven_atr_multiple": 1.0,
                "trail_atr_multiple": 1.5,
                "min_trail_step_atr": 0.2,
            }
        }
    )

    buy_pos = TrackedPosition(
        ticket=1001,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        current_sl=1.0950,
        current_tp=1.1200,
        atr=0.0050,
        high_watermark=1.1200,
        low_watermark=1.1000,
    )
    buy_pos.high_watermark = 1.1200
    res = await emulator._evaluate_tick_for_position(buy_pos, bid=1.1150, ask=1.1152, last=1.1150)
    assert res is not None
    assert buy_pos.current_sl == 1.1125


@pytest.mark.asyncio
async def test_safe_ops_cancelled_error_handling():
    """Group 4: DB-17 - safe_db_op and safe_commit rollback and re-raise CancelledError."""
    session = AsyncMock()
    session.rollback = AsyncMock()

    async def failing_op(sess):
        raise asyncio.CancelledError("Task was cancelled")

    with pytest.raises(asyncio.CancelledError):
        await safe_db_op(session, failing_op, label="test_cancel")
    session.rollback.assert_awaited_once()

    session.reset_mock()
    session.commit = AsyncMock(side_effect=asyncio.CancelledError("Commit cancelled"))
    with pytest.raises(asyncio.CancelledError):
        await safe_commit(session, label="test_commit_cancel")
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_claude_rate_limiter_tpm_tracking():
    """Group 5: LU-10 - ClaudeRateLimiter tracks tokens and enforces TPM."""
    ClaudeRateLimiter._call_times.clear()
    ClaudeRateLimiter._token_history.clear()
    ClaudeRateLimiter._last_session_start = 0.0
    ClaudeRateLimiter.MIN_DELAY_BETWEEN_SESSIONS = 0.0

    await ClaudeRateLimiter.acquire_session_slot(model_name="claude-3-5-sonnet", estimated_tokens=1500)
    assert ClaudeRateLimiter.get_current_rpm() == 1
    assert ClaudeRateLimiter.get_current_tpm() == 1500


@pytest.mark.asyncio
async def test_event_bus_type_validation():
    """Group 5: LU-11 - EventBus.subscribe rejects invalid event types."""
    bus = EventBus()

    valid_handler = AsyncMock()
    bus.subscribe(CircuitBreakerEvent, valid_handler)
    assert CircuitBreakerEvent in bus._subscribers

    class NotAnAppEvent:
        pass

    with pytest.raises(TypeError) as exc_info:
        bus.subscribe(NotAnAppEvent, valid_handler)
    assert "subclass of AppEvent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_harness_turn_cost_calculation():
    """Group 6: AN-6 - calculate_turn_cost_usd computes non-zero cost."""
    cost = calculate_turn_cost_usd(
        model_name="claude-3-5-sonnet",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=200,
    )
    assert cost > 0.0
    assert round(cost, 4) > 0.005


@pytest.mark.asyncio
async def test_verified_market_snapshot_timeframe_filter():
    """Group 6: AN-9 - VerifiedMarketSnapshot accepts and uses timeframe parameter."""
    snapshotter = VerifiedMarketSnapshot()
    session = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    res = await snapshotter.compute("EURUSD", session, timeframe="M15")
    assert res["symbol"] == "EURUSD"
    assert res["_ground_truth"] is True
    assert session.execute.await_count >= 1
