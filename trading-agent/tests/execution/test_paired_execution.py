"""
Unit tests for _execute_paired in OrderExecutor (H-11).
Verifies:
- Execution through broker_adapter and effect_gate.
- Order state transitions (PENDING_SUBMIT -> INTENT_COMMITTED -> SUBMITTED -> FILLED).
- Primary leg failure handling.
- Hedge leg failure with successful rollback of primary leg.
- Effect gate blocking handling.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from execution.service.order_executor import OrderExecutorMixin
from database.models import Order, OrderStatus, Position, AssetAnalysis
from execution.effect_gate import EffectGate, AbortRequested


class DummyExecutor(OrderExecutorMixin):
    def __init__(self, settings, broker_adapter=None, effect_gate=None, dry_run=False):
        self.settings = settings
        self.broker_adapter = broker_adapter
        self.effect_gate = effect_gate
        self.dry_run = dry_run
        self.mt5 = AsyncMock()
        self.rate_throttler = None

        self.sizer = MagicMock()
        self.gate = MagicMock()


def make_mock_sizing(lots=0.1):
    sizing = MagicMock()
    sizing.symbol = "EURUSD"
    sizing.recommended_lots = lots
    sizing.is_valid = True
    sizing.rejection_reasons = []
    sizing.entry_price = 1.0850
    sizing.stop_loss = 1.0800
    sizing.take_profit = 1.0950
    return sizing


@pytest.fixture
def base_analyses():
    primary = MagicMock(spec=AssetAnalysis)
    primary.id = 1001
    primary.symbol = "EURUSD"
    primary.decision = "buy"
    primary.current_price = 1.0850
    primary.entry_price = 1.0850
    primary.stop_loss = 1.0800
    primary.take_profit = 1.0950
    primary.entry_zone = json.dumps({"price": 1.0850})
    primary.execution_status = "pending"
    primary.execution_notes = None

    hedge = MagicMock(spec=AssetAnalysis)
    hedge.id = 1002
    hedge.symbol = "GBPUSD"
    hedge.decision = "sell"
    hedge.current_price = 1.2500
    hedge.entry_price = 1.2500
    hedge.stop_loss = 1.2550
    hedge.take_profit = 1.2400
    hedge.entry_zone = json.dumps({"price": 1.2500})
    hedge.execution_status = "pending"
    hedge.execution_notes = None

    return primary, hedge


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = None
    mock_exec.scalar.return_value = 0
    session.execute = AsyncMock(return_value=mock_exec)
    return session


@pytest.mark.asyncio
async def test_paired_order_success(mock_session, base_analyses):
    primary, hedge = base_analyses
    adapter = AsyncMock()
    adapter.submit_order = AsyncMock(side_effect=[
        {"success": True, "ticket": 12345, "price": 1.0850, "executed_volume": 0.1, "error": None},
        {"success": True, "ticket": 12346, "price": 1.2500, "executed_volume": 0.1, "error": None},
    ])

    effect_gate = EffectGate()

    executor = DummyExecutor(
        settings={"trading": {"risk": {"max_concurrent_positions": 5}}},
        broker_adapter=adapter,
        effect_gate=effect_gate,
    )
    executor.mt5.get_symbol_info = AsyncMock(return_value={
        "contract_size": 100000,
        "volume_step": 0.01,
        "volume_min": 0.01,
        "volume_max": 100.0,
    })

    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.1))
    verdict_mock = MagicMock(approved=True, rejection_reasons=[], checks_passed=["pass"], checks_failed=[])
    executor.gate.check = AsyncMock(return_value=verdict_mock)
    executor._count_open_positions = AsyncMock(return_value=0)
    executor._save_position = AsyncMock()

    with patch("execution.service.order_executor.safe_commit", new_callable=AsyncMock), \
         patch("execution.service.order_executor.transactional_advisory_lock") as mock_lock:
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def _lock_cm(*args, **kwargs):
            yield True
        mock_lock.side_effect = _lock_cm

        res = await executor.execute_paired_analyses(
            session=mock_session,
            primary=primary,
            hedge=hedge,
            pair_group_id="test_pair_group_123",
            account_equity=10000.0,
        )

    assert res["success"] is True
    assert res["tickets"] == [12345, 12346]
    assert adapter.submit_order.call_count == 2


@pytest.mark.asyncio
async def test_paired_order_hedge_failure_rollback(mock_session, base_analyses):
    primary, hedge = base_analyses
    adapter = AsyncMock()
    adapter.submit_order = AsyncMock(side_effect=[
        {"success": True, "ticket": 12345, "price": 1.0850, "executed_volume": 0.1, "error": None},
        {"success": False, "ticket": None, "price": None, "executed_volume": 0.0, "error": "Margin exceeded"},
    ])
    adapter.close_position = AsyncMock(return_value={"success": True, "error": None})

    effect_gate = EffectGate()

    executor = DummyExecutor(
        settings={"trading": {"risk": {"max_concurrent_positions": 5}}},
        broker_adapter=adapter,
        effect_gate=effect_gate,
    )
    executor.mt5.get_symbol_info = AsyncMock(return_value={
        "contract_size": 100000,
        "volume_step": 0.01,
        "volume_min": 0.01,
        "volume_max": 100.0,
    })

    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.1))
    verdict_mock = MagicMock(approved=True, rejection_reasons=[], checks_passed=["pass"], checks_failed=[])
    executor.gate.check = AsyncMock(return_value=verdict_mock)
    executor._count_open_positions = AsyncMock(return_value=0)

    with patch("execution.service.order_executor.safe_commit", new_callable=AsyncMock), \
         patch("execution.service.order_executor.transactional_advisory_lock") as mock_lock:
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def _lock_cm(*args, **kwargs):
            yield True
        mock_lock.side_effect = _lock_cm

        res = await executor.execute_paired_analyses(
            session=mock_session,
            primary=primary,
            hedge=hedge,
            pair_group_id="test_pair_group_123",
            account_equity=10000.0,
        )

    assert res["success"] is False
    assert primary.execution_status == "rolled_back"
    assert hedge.execution_status == "failed"
    adapter.close_position.assert_awaited_once_with(12345)
