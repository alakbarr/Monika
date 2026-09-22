"""
Tests for PR-15: IdempotencyGuard & Order-Position Deduplication Engine.
Verifies deterministic key generation, lock acquisition, concurrent duplicate blocking,
broker position reconciliation, and ExecutionService integration.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from execution.idempotency_guard import (
    IdempotencyGuard,
    IdempotencyState,
    get_idempotency_guard,
)
from risk.trade_proposal import TradeProposal
from execution.service.order_executor import ExecutionResult


@pytest.mark.asyncio
async def test_idempotency_key_generation():
    k1 = IdempotencyGuard.generate_key("EURUSD", "BUY", 1.0850, proposal_id="prop-123")
    k2 = IdempotencyGuard.generate_key("EURUSD", "BUY", 1.0850, proposal_id="prop-123")
    k3 = IdempotencyGuard.generate_key("EURUSD", "SELL", 1.0850, proposal_id="prop-123")

    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 24


@pytest.mark.asyncio
async def test_acquire_and_duplicate_block():
    guard = IdempotencyGuard()
    key = "test_key_01"

    # 1. First lock acquire succeeds
    ok1, reason1 = await guard.acquire_lock(key, "EURUSD", "BUY", ttl_seconds=60.0)
    assert ok1 is True
    assert reason1 is None

    # 2. Second lock acquire with same key fails (IN_FLIGHT)
    ok2, reason2 = await guard.acquire_lock(key, "EURUSD", "BUY", ttl_seconds=60.0)
    assert ok2 is False
    assert "already IN_FLIGHT" in reason2


@pytest.mark.asyncio
async def test_completed_order_blocks_duplicate():
    guard = IdempotencyGuard()
    key = "test_key_02"

    await guard.acquire_lock(key, "USDJPY", "SELL")
    await guard.mark_completed(key, ticket=987654)

    # Next attempt should be blocked as already COMPLETED
    ok, reason = await guard.acquire_lock(key, "USDJPY", "SELL")
    assert ok is False
    assert "already COMPLETED" in reason
    assert "987654" in reason


@pytest.mark.asyncio
async def test_release_lock_allows_reacquire():
    guard = IdempotencyGuard()
    key = "test_key_03"

    await guard.acquire_lock(key, "XAUUSD", "BUY")
    await guard.release_lock(key)

    # Now re-acquire should succeed
    ok, reason = await guard.acquire_lock(key, "XAUUSD", "BUY")
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_reconcile_with_broker_matches_ticket():
    guard = IdempotencyGuard()
    key = "test_key_04"

    # Order in flight with ticket in metadata
    await guard.acquire_lock(key, "GBPUSD", "BUY", metadata={"ticket": 112233})

    open_positions = [{"ticket": 112233, "symbol": "GBPUSD"}]
    matched = await guard.reconcile_with_broker(open_positions)
    assert matched == 1

    # Verify key transitioned to COMPLETED
    rec = guard._records.get(key)
    assert rec.state == IdempotencyState.COMPLETED
    assert rec.ticket == 112233


@pytest.mark.asyncio
async def test_execute_proposal_duplicate_blocked():
    # Test execute_proposal using mock service
    from execution.service.order_executor import OrderExecutorMixin

    class MockExecutionService(OrderExecutorMixin):
        def __init__(self):
            self.idempotency_guard = IdempotencyGuard()
            self.settings = {}

    service = MockExecutionService()
    service.execute_preplanned_order = AsyncMock(return_value=ExecutionResult(
        symbol="EURUSD", analysis_id=1, decision="buy", sizing=None,
        risk_approved=True, risk_checks_passed=[], risk_checks_failed=[],
        risk_rejection_reasons=[], executed=True, mt5_ticket=554433,
        executed_price=1.0850, executed_lots=0.1, mt5_error=None,
        position_id=1, timestamp=time.time(), elapsed_ms=10.0
    ))

    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0820,
        take_profit=1.0910,
        lot_size=0.1,
        proposal_id="same-uuid-1",
    )

    mock_session = AsyncMock()

    # First execution succeeds
    res1 = await service.execute_proposal(mock_session, prop)
    assert res1.executed is True
    assert res1.mt5_ticket == 554433

    # Second execution with identical proposal is blocked by IdempotencyGuard
    res2 = await service.execute_proposal(mock_session, prop)
    assert res2.executed is False
    assert "idempotency_blocked" in res2.risk_checks_failed
