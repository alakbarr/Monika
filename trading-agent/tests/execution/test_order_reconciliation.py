# ==============================================================================
# File: tests/execution/test_order_reconciliation.py
# ==============================================================================

"""
Unit & Integration Test Suite for FASE 3:
Nautilus-Grade Order Lifecycle & Reconciliation Engine.

Test Coverage:
1. Pending Limit/Stop Orders transition to ACCEPTED on broker placement.
2. PARTIALLY_FILLED state transitions and event logging when broker fills volume incrementally.
3. OrderReconciler detects terminal fill, transitions DB Order to FILLED, spawns Position,
   and publishes OrderStateChangedEvent.
4. OrderReconciler detects external cancellation/expiry and transitions DB Order to CANCELLED.
5. OrderReconciler detects external position closure, updates DB Position to 'closed',
   and creates TradeOutcome.
6. OrderReconciler syncs external modifications to SL, TP, or volume.
7. OrderReconciler adopts untracked terminal positions.
8. Background worker loop starts and stops gracefully.
"""

import asyncio
import time
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base, Order, OrderStatus, OrderEvent, Position, TradeOutcome, AssetAnalysis
)
from execution.broker_adapter import SimulatedBrokerAdapter, MT5LiveAdapter
from execution.execution_service import ExecutionService, ExecutionResult
from scheduler.order_reconciler import OrderReconciler
from utils.protocol.event_bus import get_event_bus, reset_event_bus, OrderStateChangedEvent
import utils.clock as clock


@pytest.fixture
def clean_event_bus():
    reset_event_bus()
    yield get_event_bus()
    reset_event_bus()


@pytest.fixture
async def async_sqlite_session():
    """In-memory SQLite async engine & session for testing real DB relationships."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


class TestPendingOrderAcceptedLifecycle:
    """Test transitions of pending limit/stop orders to ACCEPTED upon broker placement."""

    @pytest.mark.asyncio
    async def test_simulated_adapter_limit_order_returns_accepted(self):
        """Verify SimulatedBrokerAdapter sets pending status with assigned ticket for LIMIT orders."""
        adapter = SimulatedBrokerAdapter(initial_balance=10000.0)
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        order = Order(
            symbol="EURUSD",
            order_type="LIMIT",
            direction="BUY",
            requested_price=1.0800,  # Below market ask 1.0852 -> pending
            requested_volume=0.5,
            status=OrderStatus.SUBMITTED,
        )
        res = await adapter.submit_order(order)
        assert res["success"] is True
        assert res["status"] == "pending"
        assert res["ticket"] is not None
        assert res["executed_volume"] == 0.0

        orders = await adapter.get_orders("EURUSD")
        assert len(orders) == 1
        assert orders[0]["ticket"] == res["ticket"]

    @pytest.mark.asyncio
    async def test_mt5_live_adapter_dry_run_pending_order_returns_accepted(self):
        """Verify MT5LiveAdapter in dry_run mode returns accepted status for LIMIT orders."""
        mock_mt5 = AsyncMock()
        adapter = MT5LiveAdapter(mt5_client=mock_mt5, dry_run=True)

        order = Order(
            symbol="EURUSD",
            order_type="LIMIT",
            direction="BUY",
            requested_price=1.0800,
            requested_volume=0.2,
            status=OrderStatus.SUBMITTED,
        )
        res = await adapter.submit_order(order)
        assert res["success"] is True
        assert res["status"] == "accepted"
        assert res["ticket"] is not None
        assert res["executed_volume"] == 0.0

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_limit_order_transitions_to_accepted(
        self, async_sqlite_session, clean_event_bus
    ):
        """Verify ExecutionService transitions pending limit order to ACCEPTED with audit event."""
        session = async_sqlite_session
        bus = clean_event_bus

        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        adapter = SimulatedBrokerAdapter(initial_balance=10000.0)
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        settings = {
            "trading": {
                "min_paper_trades_before_live": 0,
                "risk": {"confluence_verifier_enabled": False, "max_open_positions": 5},
            },
            "execution": {"max_spread_multiplier": {"EURUSD": 5.0}},
        }
        svc = ExecutionService(settings=settings, broker_adapter=adapter, dry_run=False)
        svc.gate.check = AsyncMock(return_value=MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[]))

        order_plan = {
            "symbol": "EURUSD",
            "decision": "buy",
            "order_type": "limit",
            "entry_price": 1.0800,
            "stop_loss": 1.0780,
            "take_profit": 1.1000,
            "lots": 0.2,
        }

        # Submitting preplanned order with price below market
        result = await svc.execute_preplanned_order(
            session=session,
            symbol="EURUSD",
            order_plan=order_plan,
            account_equity=10000.0,
        )

        assert result.executed is True
        assert result.mt5_ticket is not None
        assert result.position_id is None  # Position is NOT opened yet

        # Verify DB Order status is ACCEPTED
        db_order = (await session.execute(select(Order).where(Order.symbol == "EURUSD"))).scalar_one()
        assert db_order.status == OrderStatus.ACCEPTED
        assert db_order.filled_volume == 0.0
        assert db_order.mt5_ticket == result.mt5_ticket

        # Verify EventBus events: PENDING_SUBMIT -> SUBMITTED -> ACCEPTED
        states = [e.new_state for e in received_events if e.order_id == db_order.id]
        assert OrderStatus.ACCEPTED.value in states


class TestPartialFillLifecycle:
    """Test partial fill handling and state transitions."""

    @pytest.mark.asyncio
    async def test_order_partial_fill_and_subsequent_complete_fill(
        self, async_sqlite_session, clean_event_bus
    ):
        """Verify incremental fill from ACCEPTED -> PARTIALLY_FILLED -> FILLED."""
        session = async_sqlite_session
        bus = clean_event_bus

        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        order = Order(
            id="ord_part_001",
            client_order_id="ORD_PART_001",
            symbol="GBPUSD",
            order_type="LIMIT",
            direction="BUY",
            requested_price=1.2650,
            requested_volume=1.0,
            status=OrderStatus.SUBMITTED,
        )
        session.add(order)
        await session.commit()

        adapter = SimulatedBrokerAdapter()
        svc = ExecutionService(settings={}, broker_adapter=adapter)

        # 1. Transition to ACCEPTED
        await svc._transition_order_state(
            session, order, OrderStatus.ACCEPTED,
            reason="Broker accepted limit order",
            ticket=200001
        )
        assert order.status == OrderStatus.ACCEPTED
        assert order.filled_volume == 0.0

        # 2. Partial fill of 0.4 lots
        await svc._transition_order_state(
            session, order, OrderStatus.PARTIALLY_FILLED,
            reason="Partial fill 0.4/1.0 lots",
            ticket=200001,
            executed_price=1.2650,
            filled_volume=0.4
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_volume == 0.4
        assert order.is_terminal is False

        # 3. Final fill of remaining 0.6 lots
        await svc._transition_order_state(
            session, order, OrderStatus.FILLED,
            reason="Remaining volume filled",
            ticket=200001,
            executed_price=1.2650,
            filled_volume=1.0
        )
        assert order.status == OrderStatus.FILLED
        assert order.filled_volume == 1.0
        assert order.is_terminal is True

        # Check recorded events
        states = [e.new_state for e in received_events if e.order_id == order.id]
        assert states == ["accepted", "partially_filled", "filled"]


class TestOrderReconcilerWorker:
    """Comprehensive test suite for the OrderReconciler background worker."""

    @pytest.mark.asyncio
    async def test_reconciler_pending_order_filled_in_terminal(
        self, async_sqlite_session, clean_event_bus
    ):
        """
        Scenario: DB has an ACCEPTED pending order.
        MT5 terminal reports that the order is no longer in pending orders,
        but an open position with the same ticket exists.
        Reconciler must:
        - Transition DB order to FILLED
        - Spawn matching Position in DB
        - Publish OrderStateChangedEvent
        """
        session = async_sqlite_session
        bus = clean_event_bus

        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        # DB order in ACCEPTED state
        order = Order(
            id="ord_rec_001",
            client_order_id="ORD_REC_001",
            symbol="USDJPY",
            order_type="LIMIT",
            direction="BUY",
            requested_price=155.20,
            requested_volume=0.3,
            status=OrderStatus.ACCEPTED,
            mt5_ticket=778899,
        )
        session.add(order)
        await session.commit()

        # Mock MT5 / Broker adapter returns:
        # No pending orders, but position 778899 exists
        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[{
            "ticket": 778899,
            "symbol": "USDJPY",
            "direction": "buy",
            "volume": 0.3,
            "price_open": 155.18,
            "sl": 154.50,
            "tp": 156.50,
            "time": clock.now(),
        }])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["orders_filled"] == 1

        # Verify DB order state
        await session.refresh(order)
        assert order.status == OrderStatus.FILLED
        assert order.executed_price == 155.18
        assert order.filled_volume == 0.3

        # Verify spawned Position record
        pos = (await session.execute(select(Position).where(Position.mt5_ticket == 778899))).scalar_one_or_none()
        assert pos is not None
        assert pos.order_id == order.id
        assert pos.symbol == "USDJPY"
        assert pos.direction == "buy"
        assert pos.volume == 0.3
        assert pos.entry_price == 155.18
        assert pos.status == "open"

        # Verify EventBus received OrderStateChangedEvent(FILLED)
        assert any(e.order_id == order.id and e.new_state == "filled" for e in received_events)

    @pytest.mark.asyncio
    async def test_reconciler_pending_order_cancelled_externally(
        self, async_sqlite_session, clean_event_bus
    ):
        """
        Scenario: DB has an ACCEPTED pending order.
        Terminal reports neither a pending order nor an open position, and no deals exist.
        Reconciler must:
        - Transition DB order to CANCELLED
        - Publish OrderStateChangedEvent
        """
        session = async_sqlite_session
        bus = clean_event_bus

        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        order = Order(
            id="ord_cancel_001",
            client_order_id="ORD_CANCEL_001",
            symbol="XAUUSD",
            order_type="LIMIT",
            direction="SELL",
            requested_price=2400.0,
            requested_volume=0.1,
            status=OrderStatus.ACCEPTED,
            mt5_ticket=889900,
        )
        session.add(order)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["orders_cancelled"] == 1

        await session.refresh(order)
        assert order.status == OrderStatus.CANCELLED
        assert any(e.order_id == order.id and e.new_state == "cancelled" for e in received_events)

    @pytest.mark.asyncio
    async def test_reconciler_pending_order_partial_fill_in_terminal(
        self, async_sqlite_session, clean_event_bus
    ):
        """
        Scenario: DB has an ACCEPTED order for 1.0 lots.
        Terminal reports the order is still pending, but volume_current is 0.6 lots (0.4 filled).
        Reconciler must:
        - Transition DB order to PARTIALLY_FILLED
        - Update filled_volume to 0.4
        - Publish OrderStateChangedEvent
        """
        session = async_sqlite_session
        bus = clean_event_bus

        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        order = Order(
            id="ord_pfill_001",
            client_order_id="ORD_PFILL_001",
            symbol="EURUSD",
            order_type="LIMIT",
            direction="BUY",
            requested_price=1.0820,
            requested_volume=1.0,
            status=OrderStatus.ACCEPTED,
            mt5_ticket=445566,
        )
        session.add(order)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[{
            "ticket": 445566,
            "symbol": "EURUSD",
            "volume_initial": 1.0,
            "volume_current": 0.6,
            "price_open": 1.0820,
        }])
        mock_adapter.get_positions = AsyncMock(return_value=[])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["orders_partially_filled"] == 1

        await session.refresh(order)
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_volume == 0.4

        assert any(e.order_id == order.id and e.new_state == "partially_filled" for e in received_events)

    @pytest.mark.asyncio
    async def test_reconciler_open_position_closed_externally(
        self, async_sqlite_session
    ):
        """
        Scenario: DB has an open Position.
        Terminal reports no open positions.
        Reconciler must:
        - Mark DB Position as 'closed'
        - Set closed_at
        - Create TradeOutcome record
        """
        session = async_sqlite_session

        pos = Position(
            mt5_ticket=121212,
            symbol="BTCUSD",
            direction="buy",
            volume=0.1,
            entry_price=65000.0,
            sl=64000.0,
            tp=67000.0,
            status="open",
            opened_at=clock.now(),
            is_paper=False,
        )
        session.add(pos)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[])
        mock_adapter.get_account_info = AsyncMock(return_value={"equity": 10000.0})

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["positions_closed"] == 1

        await session.refresh(pos)
        assert pos.status == "closed"
        assert pos.closed_at is not None

        # Verify TradeOutcome
        outcome = (await session.execute(select(TradeOutcome).where(TradeOutcome.position_id == pos.id))).scalar_one_or_none()
        assert outcome is not None
        assert outcome.symbol == "BTCUSD"
        assert outcome.exit_reason == "external_terminal_close"

    @pytest.mark.asyncio
    async def test_reconciler_preserves_paper_position_when_terminal_empty(
        self, async_sqlite_session
    ):
        """
        P0-2: Verify that paper positions (is_paper=True) are NEVER closed by
        OrderReconciler when the live MT5 terminal returns no open positions.
        """
        session = async_sqlite_session

        pos = Position(
            mt5_ticket=999888,
            symbol="EURUSD",
            direction="buy",
            volume=0.2,
            entry_price=1.0850,
            sl=1.0800,
            tp=1.0950,
            status="open",
            opened_at=clock.now(),
            is_paper=True,
        )
        session.add(pos)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[])
        mock_adapter.get_account_info = AsyncMock(return_value={"equity": 10000.0})

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["positions_closed"] == 0

        await session.refresh(pos)
        assert pos.status == "open"
        assert pos.closed_at is None

    @pytest.mark.asyncio
    async def test_reconciler_position_sltp_and_volume_modified_externally(
        self, async_sqlite_session
    ):
        """
        Scenario: DB has open Position with SL 1.0800, TP 1.0900, Vol 1.0.
        Terminal reports same position with SL 1.0820, TP 1.0950, Vol 0.5.
        Reconciler must update DB Position fields.
        """
        session = async_sqlite_session

        pos = Position(
            mt5_ticket=343434,
            symbol="EURUSD",
            direction="buy",
            volume=1.0,
            entry_price=1.0850,
            sl=1.0800,
            tp=1.0900,
            status="open",
            opened_at=clock.now(),
            is_paper=False,
        )
        session.add(pos)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[{
            "ticket": 343434,
            "symbol": "EURUSD",
            "sl": 1.0820,
            "tp": 1.0950,
            "volume": 0.5,
        }])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["positions_modified"] == 1

        await session.refresh(pos)
        assert pos.sl == 1.0820
        assert pos.tp == 1.0950
        assert pos.volume == 0.5

    @pytest.mark.asyncio
    async def test_reconciler_adopts_untracked_terminal_position(
        self, async_sqlite_session
    ):
        """
        Scenario: Terminal has a position #{565656} that is not recorded in local DB.
        Reconciler must adopt it and create an open Position record.
        """
        session = async_sqlite_session

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[{
            "ticket": 565656,
            "symbol": "XTIUSD",
            "direction": "sell",
            "volume": 0.2,
            "price_open": 78.50,
            "sl": 80.0,
            "tp": 75.0,
            "time": clock.now(),
        }])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats["untracked_adopted"] == 1

        adopted = (await session.execute(select(Position).where(Position.mt5_ticket == 565656))).scalar_one_or_none()
        assert adopted is not None
        assert adopted.symbol == "XTIUSD"
        assert adopted.direction == "sell"
        assert adopted.volume == 0.2
        assert adopted.entry_price == 78.50
        assert adopted.status == "open"

    @pytest.mark.asyncio
    async def test_reconciler_start_and_stop_gracefully(self):
        """Verify reconciler background loop runs and stops cleanly."""
        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
            interval_seconds=0.05,
        )

        task = asyncio.create_task(reconciler.start())
        await asyncio.sleep(0.12)
        assert mock_adapter.get_orders.call_count >= 1

        reconciler.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert task.done()


class TestMainOrchestrationIntegration:
    """Test that TradingAgent in main.py wires OrderReconciler cleanly."""

    def test_trading_agent_initializes_order_reconciler(self):
        """Verify TradingAgent creates OrderReconciler attribute in _init_components."""
        from main import TradingAgent

        settings = {
            "trading": {"dry_run": True},
            "execution": {"reconciliation_interval_seconds": 20},
        }
        agent = TradingAgent(settings=settings, dry_run=True)
        assert hasattr(agent, "order_reconciler")
        assert agent.order_reconciler is None

        # Call _init_components with mocked dependencies
        with patch("execution.mt5_client.MT5Client"), \
             patch("execution.execution_service.ExecutionService"), \
             patch("execution.ea_bridge.heartbeat_writer.HeartbeatManager"), \
             patch("scheduler.graph_cycle_scheduler.GraphCycleScheduler"), \
             patch("scheduler.news_watcher.NewsWatcher"), \
             patch("telegram_bot.bot.TelegramBot"), \
             patch("analysis.stages.fundamental_stage.FundamentalStage"), \
             patch("analysis.stages.per_asset_stage.PerAssetStage"), \
             patch("scheduler.market_data_scheduler.MarketDataScheduler"), \
             patch("scheduler.macro_data_scheduler.MacroDataScheduler"), \
             patch("scheduler.trigger_checker.TriggerChecker"):
            agent._init_components()

        assert agent.order_reconciler is not None
        assert isinstance(agent.order_reconciler, OrderReconciler)
        assert agent.order_reconciler.interval_seconds == 20.0


class TestReconcilerHardenedEdgeCases:
    """Rigorous edge-case tests validating robustness, safety, and accounting parity."""

    def test_mt5_remote_gateway_adapter_instantiation_and_get_orders(self):
        """Verify MT5RemoteGatewayAdapter can be instantiated without TypeError."""
        from execution.broker_adapter import MT5RemoteGatewayAdapter
        adapter = MT5RemoteGatewayAdapter(gateway_url="http://localhost:8080")
        assert hasattr(adapter, "get_orders")
        assert callable(adapter.get_orders)

    @pytest.mark.asyncio
    async def test_reconciler_aborts_on_terminal_disconnect_preserving_db_state(
        self, async_sqlite_session
    ):
        """
        Verify that if broker/MT5 fails or is disconnected, the reconciler
        skips the pass and DOES NOT falsely mark positions closed or orders cancelled.
        """
        session = async_sqlite_session

        # 1 open position and 1 accepted order in DB
        pos = Position(
            mt5_ticket=555111,
            symbol="EURUSD",
            direction="buy",
            volume=0.5,
            entry_price=1.0850,
            status="open",
        )
        order = Order(
            id="ord_safe_01",
            symbol="EURUSD",
            direction="BUY",
            order_type="LIMIT",
            requested_price=1.0800,
            requested_volume=0.5,
            status=OrderStatus.ACCEPTED,
            mt5_ticket=555222,
        )
        session.add_all([pos, order])
        await session.commit()

        # Mock adapter raising an exception / disconnected
        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(side_effect=ConnectionError("MT5 Bridge Offline"))
        mock_adapter.get_positions = AsyncMock(side_effect=ConnectionError("MT5 Bridge Offline"))

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats.get("skipped") is True
        assert stats.get("reason") == "terminal_unavailable"

        # Verify DB records are completely untouched!
        await session.refresh(pos)
        await session.refresh(order)
        assert pos.status == "open"
        assert order.status == OrderStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_reconciler_preserves_newly_submitted_order_within_grace_period(
        self, async_sqlite_session
    ):
        """
        Verify that a newly SUBMITTED order (<45s old) is NOT immediately cancelled
        if it has not yet appeared in the terminal.
        """
        session = async_sqlite_session

        order = Order(
            id="ord_grace_01",
            symbol="GBPUSD",
            direction="BUY",
            order_type="LIMIT",
            requested_price=1.2600,
            requested_volume=0.2,
            status=OrderStatus.SUBMITTED,
            created_at=clock.now(),
        )
        session.add(order)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}, "execution": {"reconciliation": {"submitted_grace_seconds": 45.0}}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats.get("orders_cancelled", 0) == 0

        await session.refresh(order)
        assert order.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_reconciler_handles_order_with_none_ticket_without_matching_null_position(
        self, async_sqlite_session
    ):
        """
        Verify that order with mt5_ticket=None does not match a Position with mt5_ticket=None
        due to 'IS NULL' SQL evaluation.
        """
        session = async_sqlite_session

        # Existing unrelated position with mt5_ticket=None
        unrelated_pos = Position(
            id=991,
            order_id="unrelated_ord_id",
            mt5_ticket=None,
            symbol="USDCHF",
            direction="buy",
            volume=0.1,
            entry_price=0.8800,
            status="open",
        )
        # Order with mt5_ticket=None, filled into terminal position #999001
        order = Order(
            id="ord_null_ticket_01",
            client_order_id="ORD_NULL_01",
            symbol="EURUSD",
            direction="BUY",
            order_type="LIMIT",
            requested_price=1.0850,
            requested_volume=0.2,
            status=OrderStatus.SUBMITTED,
            mt5_ticket=None,
        )
        session.add_all([unrelated_pos, order])
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        # Terminal position has comment containing order's client_order_id
        mock_adapter.get_positions = AsyncMock(return_value=[{
            "ticket": 999001,
            "symbol": "EURUSD",
            "direction": "buy",
            "volume": 0.2,
            "price_open": 1.0850,
            "comment": "ORD_NULL_01",
            "time": clock.now(),
        }])

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        stats = await reconciler.reconcile_once(session=session)
        assert stats.get("orders_filled") == 1

        await session.refresh(order)
        assert order.status == OrderStatus.FILLED
        assert order.mt5_ticket == 999001

        # Spawned position should have ticket 999001 and order_id ord_null_ticket_01
        new_pos = (await session.execute(select(Position).where(Position.order_id == order.id))).scalar_one_or_none()
        assert new_pos is not None
        assert new_pos.mt5_ticket == 999001

    @pytest.mark.asyncio
    async def test_reconciler_prevents_duplicate_trade_outcome(
        self, async_sqlite_session
    ):
        """Verify multiple reconciliation passes on closed position do not duplicate TradeOutcome."""
        session = async_sqlite_session

        pos = Position(
            id=882,
            mt5_ticket=666777,
            symbol="AUDUSD",
            direction="sell",
            volume=0.2,
            entry_price=0.6500,
            status="open",
        )
        session.add(pos)
        await session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.get_orders = AsyncMock(return_value=[])
        mock_adapter.get_positions = AsyncMock(return_value=[])  # Position closed in terminal
        mock_adapter.get_account_info = AsyncMock(return_value={"equity": 10000.0})

        reconciler = OrderReconciler(
            settings={"trading": {"dry_run": False}},
            broker_adapter=mock_adapter,
        )

        # First pass closes position and creates TradeOutcome
        stats1 = await reconciler.reconcile_once(session=session)
        assert stats1.get("positions_closed") == 1

        outcomes1 = (await session.execute(select(TradeOutcome).where(TradeOutcome.position_id == pos.id))).scalars().all()
        assert len(outcomes1) == 1

        # Second pass should not duplicate TradeOutcome
        stats2 = await reconciler.reconcile_once(session=session)
        assert stats2.get("positions_closed") == 0

        outcomes2 = (await session.execute(select(TradeOutcome).where(TradeOutcome.position_id == pos.id))).scalars().all()
        assert len(outcomes2) == 1

    @pytest.mark.asyncio
    async def test_mt5_live_adapter_cancel_order_resolves_string_client_order_id(self):
        """Verify MT5LiveAdapter.cancel_order resolves string client_order_id to numeric ticket."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_orders = AsyncMock(return_value=[{
            "ticket": 444333,
            "comment": "ORD#ord_abc1",
            "client_order_id": "ord_abc1",
            "symbol": "EURUSD",
        }])
        mock_mt5.cancel_order = AsyncMock(return_value={"success": True, "ticket": 444333})

        adapter = MT5LiveAdapter(mt5_client=mock_mt5, dry_run=False)
        res = await adapter.cancel_order("ord_abc1")
        assert res is True
        mock_mt5.cancel_order.assert_called_once_with(444333)

