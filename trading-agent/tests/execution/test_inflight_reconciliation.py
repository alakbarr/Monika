# ==============================================================================
# File: tests/execution/test_inflight_reconciliation.py
# ==============================================================================

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from database.models import Order, OrderStatus
from execution.execution_service import ExecutionService


@pytest.mark.asyncio
async def test_reconcile_inflight_orders_none_found():
    svc = ExecutionService(settings={}, dry_run=True)

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch("execution.service.position_synchronizer.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = session
        res = await svc.reconcile_inflight_orders()

    assert res["total"] == 0
    assert res["reconciled"] == 0
    assert res["interrupted"] == 0


@pytest.mark.asyncio
async def test_reconcile_inflight_orders_matched_at_broker():
    svc = ExecutionService(settings={}, dry_run=True)

    order = Order(
        symbol="EURUSD",
        order_type="MARKET",
        direction="BUY",
        requested_price=1.0850,
        requested_volume=0.1,
    )
    order.status = OrderStatus.SUBMITTED

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [order]
    session.execute = AsyncMock(return_value=mock_result)

    # Mock broker positions returning matching open position
    svc.broker_adapter.get_positions = AsyncMock(return_value=[
        {
            "symbol": "EURUSD",
            "type": "buy",
            "volume": 0.1,
            "open_price": 1.0852,
            "ticket": 987654,
        }
    ])

    with patch("execution.service.position_synchronizer.get_session") as mock_get_session, \
         patch("execution.service.position_synchronizer.AgentNotifier") as mock_notif_cls:
        mock_get_session.return_value.__aenter__.return_value = session
        mock_notifier = MagicMock()
        mock_notifier.send_critical = AsyncMock()
        mock_notif_cls.return_value = mock_notifier

        res = await svc.reconcile_inflight_orders()

    assert res["total"] == 1
    assert res["reconciled"] == 1
    assert res["interrupted"] == 0
    assert order.status == OrderStatus.FILLED
    assert order.mt5_ticket == 987654
    assert order.executed_price == 1.0852
    assert order.settlement_committed_at is not None


@pytest.mark.asyncio
async def test_reconcile_inflight_orders_not_at_broker_marked_interrupted():
    svc = ExecutionService(settings={}, dry_run=True)

    order = Order(
        symbol="GBPUSD",
        order_type="MARKET",
        direction="SELL",
        requested_price=1.2600,
        requested_volume=0.2,
    )
    order.status = OrderStatus.INTENT_COMMITTED

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [order]
    session.execute = AsyncMock(return_value=mock_result)

    # Broker has NO matching position
    svc.broker_adapter.get_positions = AsyncMock(return_value=[])

    with patch("execution.service.position_synchronizer.get_session") as mock_get_session, \
         patch("execution.service.position_synchronizer.AgentNotifier") as mock_notif_cls:
        mock_get_session.return_value.__aenter__.return_value = session
        mock_notifier = MagicMock()
        mock_notifier.send_critical = AsyncMock()
        mock_notif_cls.return_value = mock_notifier

        res = await svc.reconcile_inflight_orders()

    assert res["total"] == 1
    assert res["reconciled"] == 0
    assert res["interrupted"] == 1
    assert order.status == OrderStatus.INTERRUPTED
    assert order.is_terminal is True


@pytest.mark.asyncio
async def test_reconcile_inflight_orders_creates_position_record():
    from database.models import Position
    svc = ExecutionService(settings={}, dry_run=True)

    order = Order(
        symbol="EURUSD",
        order_type="MARKET",
        direction="BUY",
        requested_price=1.0850,
        requested_volume=0.1,
    )
    order.status = OrderStatus.SUBMITTED

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [order]
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    svc.broker_adapter.get_positions = AsyncMock(return_value=[
        {
            "symbol": "EURUSD",
            "type": "buy",
            "volume": 0.1,
            "open_price": 1.0852,
            "ticket": 123456,
        }
    ])

    with patch("execution.service.position_synchronizer.get_session") as mock_get_session, \
         patch("execution.service.position_synchronizer.AgentNotifier"):
        mock_get_session.return_value.__aenter__.return_value = session
        res = await svc.reconcile_inflight_orders()

    assert res["reconciled"] == 1
    assert order.status == OrderStatus.FILLED
    # Verify session.add was called with a Position instance
    added_positions = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Position)]
    assert len(added_positions) >= 1
    assert added_positions[0].mt5_ticket == 123456
    assert added_positions[0].symbol == "EURUSD"


@pytest.mark.asyncio
async def test_reconcile_inflight_orders_pending_order_retains_submitted():
    svc = ExecutionService(settings={}, dry_run=True)

    order = Order(
        symbol="XAUUSD",
        order_type="LIMIT",
        direction="BUY",
        requested_price=2300.0,
        requested_volume=0.05,
    )
    order.status = OrderStatus.SUBMITTED

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [order]
    session.execute = AsyncMock(return_value=mock_result)

    # Broker has NO open positions, but HAS pending order
    svc.broker_adapter.get_positions = AsyncMock(return_value=[])
    svc.broker_adapter.get_orders = AsyncMock(return_value=[
        {
            "symbol": "XAUUSD",
            "type": "buy_limit",
            "volume": 0.05,
            "price_open": 2300.0,
            "ticket": 777888,
        }
    ])

    with patch("execution.service.position_synchronizer.get_session") as mock_get_session, \
         patch("execution.service.position_synchronizer.AgentNotifier"):
        mock_get_session.return_value.__aenter__.return_value = session
        res = await svc.reconcile_inflight_orders()

    assert res["reconciled"] == 1
    assert res["interrupted"] == 0
    assert order.status == OrderStatus.SUBMITTED
    assert order.mt5_ticket == 777888
