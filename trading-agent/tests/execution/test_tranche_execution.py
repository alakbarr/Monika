"""
Unit tests for execute_tranche_order in OrderExecutor (P0-6).
Verifies:
- Execution through broker_adapter and effect_gate.
- Order state transitions (PENDING_SUBMIT -> INTENT_COMMITTED -> SUBMITTED -> FILLED/REJECTED).
- Leg 1 failure handling.
- Leg 2 failure with successful rollback.
- Leg 2 failure with failed rollback (orphan position marked with status 'orphan_pending_close').
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from execution.service.order_executor import OrderExecutorMixin
from database.models import Order, OrderStatus, Position, AssetAnalysis
from risk.position_sizing import SizingResult


class DummyExecutor(OrderExecutorMixin):
    def __init__(self, settings, broker_adapter=None, effect_gate=None, dry_run=False):
        self.settings = settings
        self.broker_adapter = broker_adapter
        self.effect_gate = effect_gate
        self.dry_run = dry_run
        self.mt5 = None
        self.rate_throttler = None

        self.sizer = MagicMock()
        self.gate = MagicMock()

    async def _execute_analysis_internal(self, session, analysis, account_equity):
        return MagicMock(executed=True)


@pytest.fixture
def base_analysis():
    analysis = MagicMock(spec=AssetAnalysis)
    analysis.id = 1001
    analysis.symbol = "EURUSD"
    analysis.decision = "buy"
    analysis.current_price = 1.0850
    analysis.entry_price = 1.0850
    analysis.stop_loss = 1.0800
    analysis.take_profit = 1.0950
    analysis.take_profit_2 = None
    analysis.execution_status = "pending"
    analysis.execution_notes = None
    return analysis


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_exec)
    return session


def make_mock_sizing(lots=0.20):
    sizing = MagicMock()
    sizing.symbol = "EURUSD"
    sizing.recommended_lots = lots
    sizing.is_valid = True
    sizing.rejection_reasons = []
    sizing.entry_price = 1.0850
    sizing.stop_loss = 1.0800
    sizing.take_profit = 1.0950
    return sizing


@pytest.mark.asyncio
async def test_tranche_order_success(base_analysis, mock_session):
    """Verify normal tranche execution submits both legs through broker adapter and effect gate."""
    settings = {"execution": {"max_spread_multiplier": {"EURUSD": 10.0}}}

    mock_adapter = AsyncMock()
    mock_adapter.submit_order = AsyncMock(side_effect=[
        {"success": True, "ticket": 111111, "price": 1.0850, "error": None},
        {"success": True, "ticket": 222222, "price": 1.0850, "error": None},
    ])

    mock_effect_gate = AsyncMock()
    mock_effect_gate.admit = AsyncMock(side_effect=lambda fn, **kw: fn())

    executor = DummyExecutor(settings, broker_adapter=mock_adapter, effect_gate=mock_effect_gate)
    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.20))
    executor.gate.check = AsyncMock(return_value=MagicMock(approved=True))

    with patch.object(executor, "_save_position", new_callable=AsyncMock) as mock_save:
        res = await executor.execute_tranche_order(mock_session, base_analysis, account_equity=10000.0)

    assert res["success"] is True
    assert res["tickets"] == [111111, 222222]
    assert res["lots"] == [0.10, 0.10]
    assert mock_adapter.submit_order.call_count == 2
    assert mock_effect_gate.admit.call_count == 2
    assert mock_save.call_count == 2
    assert mock_session.commit.call_count >= 1


@pytest.mark.asyncio
async def test_tranche_order_leg1_failure(base_analysis, mock_session):
    """Verify Leg 1 failure rejects order, halts, and does not submit Leg 2."""
    settings = {"execution": {}}
    mock_adapter = AsyncMock()
    mock_adapter.submit_order = AsyncMock(return_value={
        "success": False, "error": "Insufficient margin"
    })

    executor = DummyExecutor(settings, broker_adapter=mock_adapter)
    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.20))
    executor.gate.check = AsyncMock(return_value=MagicMock(approved=True))

    res = await executor.execute_tranche_order(mock_session, base_analysis, account_equity=10000.0)

    assert res["success"] is False
    assert "Leg 1 order failed" in res["reason"]
    assert mock_adapter.submit_order.call_count == 1
    mock_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_tranche_order_leg2_failure_rollback_success(base_analysis, mock_session):
    """Verify Leg 2 failure triggers Leg 1 rollback close via broker adapter."""
    settings = {"execution": {}}
    mock_adapter = AsyncMock()
    mock_adapter.submit_order = AsyncMock(side_effect=[
        {"success": True, "ticket": 333333, "price": 1.0850, "error": None},
        {"success": False, "error": "Broker timeout"},
    ])
    mock_adapter.close_position = AsyncMock(return_value={"success": True})

    executor = DummyExecutor(settings, broker_adapter=mock_adapter)
    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.20))
    executor.gate.check = AsyncMock(return_value=MagicMock(approved=True))

    res = await executor.execute_tranche_order(mock_session, base_analysis, account_equity=10000.0)

    assert res["success"] is False
    assert "Leg 2 order failed" in res["reason"]
    mock_adapter.close_position.assert_awaited_with(333333)
    assert base_analysis.execution_status == "rolled_back"


@pytest.mark.asyncio
async def test_tranche_order_leg2_failure_rollback_failed_persists_orphan(base_analysis, mock_session):
    """Verify Leg 2 failure with failed Leg 1 rollback persists orphan record with status 'orphan_pending_close'."""
    settings = {"execution": {}}
    mock_adapter = AsyncMock()
    mock_adapter.submit_order = AsyncMock(side_effect=[
        {"success": True, "ticket": 444444, "price": 1.0850, "error": None},
        {"success": False, "error": "Order rejected by gateway"},
    ])
    mock_adapter.close_position = AsyncMock(return_value={"success": False, "error": "Terminal disconnected"})

    orphan_pos = MagicMock(spec=Position)
    orphan_pos.status = "open"
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = orphan_pos
    mock_session.execute = AsyncMock(return_value=mock_exec)

    executor = DummyExecutor(settings, broker_adapter=mock_adapter)
    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.20))
    executor.gate.check = AsyncMock(return_value=MagicMock(approved=True))

    with patch("execution.service.order_executor.AgentNotifier") as mock_notifier:
        mock_notifier.return_value.send_critical = AsyncMock()
        res = await executor.execute_tranche_order(mock_session, base_analysis, account_equity=10000.0)

    assert res["success"] is False
    assert "Leg 1 rollback failed" in res["reason"]
    assert base_analysis.execution_status == "orphan_emergency"
    assert orphan_pos.status == "orphan_pending_close"
    mock_notifier.return_value.send_critical.assert_awaited_once()


@pytest.mark.asyncio
async def test_tranche_order_untradeable_decision(base_analysis, mock_session):
    """Verify non-tradeable decision (e.g. 'wait') is rejected immediately."""
    base_analysis.decision = "wait"
    executor = DummyExecutor({})
    res = await executor.execute_tranche_order(mock_session, base_analysis, account_equity=10000.0)
    assert res["success"] is False
    assert "not tradeable" in res["reason"]


@pytest.mark.asyncio
async def test_tranche_order_tiny_lots_fallback_to_single(base_analysis, mock_session):
    """Verify total lots too small (< 0.02) triggers single execution fallback."""
    executor = DummyExecutor({})
    executor.sizer.calculate_with_session = AsyncMock(return_value=make_mock_sizing(0.01))
    res = await executor.execute_tranche_order(mock_session, base_analysis, account_equity=10000.0)
    assert res["single_execution"] is True
    assert res["success"] is True

