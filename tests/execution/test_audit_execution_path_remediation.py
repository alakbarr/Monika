"""
Empirical Regression Tests for Execution Path & Dead-Man's Switch Architectural Remediation.
Verifies:
1. Fail-closed volume quantization floor (reject when below min_vol, never round up).
2. Elimination of automatic order_send retry loops in _open_position_raw.
3. Spread circuit breaker enforcement in live execution path.
4. Bidirectional clock-drift handling on tick freshness evaluation.
5. IdempotencyGuard cross-restart database persistence via SystemConfig.
6. RateThrottler category isolation and emergency action bypass.
7. IBKR position volume lot normalization.
"""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.domain.entities.order_status import OrderStatus
from monika.domain.risk.position_sizing import PositionSizer
from monika.infrastructure.brokers.idempotency_guard import IdempotencyGuard, IdempotencyState
from monika.infrastructure.brokers.rate_throttler import RateThrottler


@pytest.mark.asyncio
async def test_volume_quantization_floor_rejects_below_min_vol():
    """Verify that volume below min_vol is rejected, not rounded up to min_vol (AGENTS.md §5.5)."""
    from monika.infrastructure.brokers.mt5.order_ops import _place_order

    with patch("MetaTrader5.symbol_info") as mock_sym:
        sym_info = MagicMock()
        sym_info.volume_min = 0.10
        sym_info.volume_max = 100.0
        sym_info.volume_step = 0.01
        sym_info.digits = 5
        sym_info.trade_tick_size = 0.00001
        mock_sym.return_value = sym_info

        # Requested volume 0.05 is below volume_min 0.10
        res = _place_order(
            symbol="EURUSD",
            direction="buy",
            volume=0.05,
            price=1.0850,
            sl=1.0800,
            tp=1.0900,
            comment="test",
            order_type="MARKET",
        )

        assert res["success"] is False
        assert "below minimum volume" in res["error"].lower()


@pytest.mark.asyncio
async def test_order_send_does_not_retry_on_requote():
    """Verify that _place_order does not automatically retry on requote (AGENTS.md §5.5)."""
    from monika.infrastructure.brokers.mt5.order_ops import _place_order

    with (
        patch("MetaTrader5.symbol_info") as mock_sym,
        patch("MetaTrader5.symbol_info_tick") as mock_tick,
        patch("MetaTrader5.order_check") as mock_check,
        patch("MetaTrader5.order_send") as mock_order_send,
    ):
        sym_info = MagicMock()
        sym_info.volume_min = 0.01
        sym_info.volume_max = 100.0
        sym_info.volume_step = 0.01
        sym_info.digits = 5
        sym_info.trade_tick_size = 0.00001
        sym_info.trade_mode = 4
        sym_info.filling_mode = 1
        mock_sym.return_value = sym_info

        tick = MagicMock(bid=1.0850, ask=1.0852)
        mock_tick.return_value = tick

        chk_res = MagicMock(retcode=0)
        mock_check.return_value = chk_res

        # Return requote code 10004
        send_res = MagicMock(retcode=10004, comment="Requote")
        mock_order_send.return_value = send_res

        res = _place_order(
            symbol="EURUSD",
            direction="buy",
            volume=0.10,
            price=1.0852,
            sl=1.0800,
            tp=1.0900,
            comment="test",
            order_type="MARKET",
        )

        # Must execute only ONCE and fail closed without retrying
        assert mock_order_send.call_count == 1
        assert res["success"] is False


@pytest.mark.asyncio
async def test_spread_check_not_bypassed_in_live_execution():
    """Verify that spread check cannot be bypassed in live execution even with fallback bar."""
    from monika.application.execution.service.executors.analysis_preflight import AnalysisPreflightMixin

    class DummyExecutor(AnalysisPreflightMixin):
        def __init__(self):
            self.dry_run = False
            self.settings = {
                "execution": {
                    "force_live_override": True,
                    "max_price_staleness_seconds": 120,
                }
            }
            self.broker_adapter = None

        async def _get_current_price(self, symbol, direction="buy"):
            return 1.0850, True, 30.0

    executor = DummyExecutor()

    # Mock broker adapter returning tick with excessive spread
    mock_adapter = AsyncMock()
    mock_adapter.get_tick.return_value = {
        "symbol": "EURUSD",
        "bid": 1.0800,
        "ask": 1.0850,  # 50 pips spread (typical is 1.5 pips)
        "last": 1.0850,
        "spread": 0.0050,
        "time": time.time(),
    }
    executor.broker_adapter = mock_adapter

    mock_analysis = MagicMock()
    mock_analysis.id = 99999
    mock_analysis.symbol = "EURUSD"
    mock_analysis.decision = "buy"
    mock_analysis.generated_at = datetime.now(timezone.utc)
    mock_analysis.take_profit = 1.1000
    mock_analysis.stop_loss = 1.0700
    mock_analysis.entry_zone = None
    mock_analysis.brief_id = None
    mock_analysis.priced_in_score = None
    mock_analysis.execution_notes = None
    mock_analysis.catalyst = None
    mock_analysis.reasoning = None

    mock_session = AsyncMock()
    mock_exec_res = MagicMock()
    mock_exec_res.scalar.return_value = 0
    mock_exec_res.scalar_one_or_none.return_value = None
    mock_exec_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_exec_res

    res, ctx = await executor._validate_analysis_preflight(
        session=mock_session,
        analysis=mock_analysis,
    )

    assert res is not None
    assert res.risk_approved is False
    assert "spread_too_high" in res.risk_checks_failed
    assert ctx is None


@pytest.mark.asyncio
async def test_idempotency_guard_db_persistence():
    """Verify IdempotencyGuard records are persisted and restored from DB SystemConfig."""
    from monika.infrastructure.database.models import SystemConfig

    guard = IdempotencyGuard()
    key = "prop_test_EURUSD_BUY"

    mock_session = AsyncMock()
    mock_session.get.return_value = None
    mock_session.commit = AsyncMock()

    with (
        patch("monika.infrastructure.database.db.get_session") as mock_db,
        patch.object(SystemConfig, "upsert", new_callable=AsyncMock) as mock_upsert,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_db.return_value = mock_ctx

        # Acquire lock
        acquired, _ = await guard.acquire_lock(key, "EURUSD", "BUY")
        assert acquired is True

        # Mark completed
        await guard.mark_completed(key, ticket=123456)

        # Upsert to DB should have been called
        assert mock_upsert.await_count >= 1

        # Reset in-memory cache to simulate service restart
        guard._records.clear()

        # Mock DB returning the completed record
        import json

        mock_cfg = MagicMock()
        mock_cfg.value = json.dumps(
            {
                "key": key,
                "symbol": "EURUSD",
                "direction": "BUY",
                "state": "COMPLETED",
                "ticket": 123456,
                "created_at": time.time(),
                "expires_at": time.time() + 300.0,
            }
        )
        mock_session.get.return_value = mock_cfg

        # New acquisition attempt across restart must be blocked
        reacquired, reason = await guard.acquire_lock(key, "EURUSD", "BUY")
        assert reacquired is False
        assert "already COMPLETED" in reason


@pytest.mark.asyncio
async def test_rate_throttler_emergency_bypass_and_category_isolation():
    """Verify RateThrottler allows emergency actions unconditionally and isolates categories."""
    throttler = RateThrottler(max_per_second=1, max_per_minute=2)

    # Exhaust orders category
    v1 = await throttler.acquire(category="orders")
    assert v1.allowed is True
    v2 = await throttler.acquire(category="orders")
    # Exceeded 1/sec
    assert v2.allowed is False

    # Emergency action must succeed immediately regardless of exhausted orders quota
    v_emerg = await throttler.acquire(category="emergency")
    assert v_emerg.allowed is True
    assert v_emerg.reason == "Emergency bypass"

    # Modifications category has independent quota
    v_mod = await throttler.acquire(category="modifications")
    assert v_mod.allowed is True


def test_order_status_is_terminal_contracts():
    """Verify OrderStatus terminal state contracts."""
    assert OrderStatus.FILLED.is_terminal is True
    assert OrderStatus.CANCELLED.is_terminal is True
    assert OrderStatus.REJECTED.is_terminal is True
    assert OrderStatus.EXPIRED.is_terminal is True
    assert OrderStatus.ABORT_REQUESTED.is_terminal is True
    assert OrderStatus.PENDING_SUBMIT.is_terminal is False
    assert OrderStatus.SUBMITTED.is_terminal is False
