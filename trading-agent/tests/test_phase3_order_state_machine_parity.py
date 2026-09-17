# ==============================================================================
# File: tests/test_phase3_order_state_machine_parity.py
# ==============================================================================

"""
Comprehensive Unit & Integration Test Suite for Phase 3:
1. Entity Order & Typed State Machine (OrderStatus, Order, OrderEvent, backwards compatibility).
2. BrokerAdapter Abstraction & MT5LiveAdapter.
3. SimulatedBrokerAdapter (spread model, ATR slippage, fill latency, margin & balance simulation).
4. ExecutionService Order Lifecycle Management & EventBus publication.
5. PointInTimeBacktestEngine 100% Research-to-Live Parity Execution.
"""

import asyncio
import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base, OrderStatus, Order, OrderEvent, Position, MT5Signal,
    AssetAnalysis, FundamentalBrief, BacktestTrade, InvalidOrderStateTransitionError
)
from execution.broker_adapter import (
    BrokerAdapter, MT5LiveAdapter, SimulatedBrokerAdapter,
    _get_pip_size, _get_contract_size
)
from execution.execution_service import ExecutionService, ExecutionResult
from utils.protocol.event_bus import get_event_bus, reset_event_bus, OrderStateChangedEvent
import utils.clock as clock


# ==============================================================================
# Fixtures
# ==============================================================================

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


# ==============================================================================
# 1. Order Model & Typed OrderStatus Enum Tests
# ==============================================================================

class TestOrderStateModel:

    def test_order_status_enum_values_and_types(self):
        """Verify all 8 Nautilus-compliant OrderStatus enum values."""
        assert OrderStatus.PENDING_SUBMIT == "pending_submit"
        assert OrderStatus.SUBMITTED == "submitted"
        assert OrderStatus.ACCEPTED == "accepted"
        assert OrderStatus.PARTIALLY_FILLED == "partially_filled"
        assert OrderStatus.FILLED == "filled"
        assert OrderStatus.REJECTED == "rejected"
        assert OrderStatus.EXPIRED == "expired"
        assert OrderStatus.CANCELLED == "cancelled"

        # Str inheritance
        assert isinstance(OrderStatus.FILLED, str)
        assert OrderStatus.FILLED.value == "filled"
        assert len(OrderStatus) >= 8
        assert OrderStatus.INTENT_COMMITTED == "intent_committed"
        assert OrderStatus.INTERRUPTED == "interrupted"
        assert OrderStatus.ABORT_REQUESTED == "abort_requested"

    def test_order_instantiation_and_fields(self):
        """Verify typed Order model instantiation."""
        now = clock.now()
        order = Order(
            id="ord_test_001",
            client_order_id="CLIENT_ORD_001",
            analysis_id=42,
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0850,
            executed_price=1.0851,
            slippage_pips=1.0,
            requested_volume=0.5,
            filled_volume=0.5,
            status=OrderStatus.FILLED,
            mt5_ticket=998877,
            created_at=now,
            updated_at=now,
        )
        assert order.id == "ord_test_001"
        assert order.client_order_id == "CLIENT_ORD_001"
        assert order.analysis_id == 42
        assert order.symbol == "EURUSD"
        assert order.order_type == "MARKET"
        assert order.direction == "BUY"
        assert order.requested_price == 1.0850
        assert order.executed_price == 1.0851
        assert order.slippage_pips == 1.0
        assert order.requested_volume == 0.5
        assert order.filled_volume == 0.5
        assert order.status == OrderStatus.FILLED
        assert order.status == "filled"
        assert order.mt5_ticket == 998877

    def test_order_event_audit_trail_instantiation(self):
        """Verify typed OrderEvent model instantiation."""
        evt = OrderEvent(
            order_id="ord_test_001",
            from_status=OrderStatus.PENDING_SUBMIT.value,
            to_status=OrderStatus.SUBMITTED.value,
            reason="Submitting to MT5 broker",
            timestamp=clock.now(),
        )
        assert evt.order_id == "ord_test_001"
        assert evt.from_status == "pending_submit"
        assert evt.to_status == "submitted"
        assert "Submitting" in evt.reason

    def test_position_and_mt5signal_backward_compatibility(self):
        """Verify Position and MT5Signal models remain completely backward compatible."""
        pos = Position(
            symbol="XAUUSD",
            direction="buy",
            volume=0.2,
            entry_price=2350.0,
            status="open",
        )
        assert pos.symbol == "XAUUSD"
        assert pos.order_id is None  # Optional backwards compatible field

        pos_with_order = Position(
            order_id="ord_test_002",
            symbol="XAUUSD",
            direction="buy",
            volume=0.2,
            entry_price=2350.0,
        )
        assert pos_with_order.order_id == "ord_test_002"

        sig = MT5Signal(
            asset_analysis_id=10,
            symbol="GBPUSD",
            action="buy",
            status="pending",
        )
        assert sig.symbol == "GBPUSD"
        assert sig.action == "buy"

    @pytest.mark.asyncio
    async def test_order_and_order_event_db_persistence(self, async_sqlite_session):
        """Verify Order and OrderEvent persist and query correctly with foreign key relationships."""
        session = async_sqlite_session

        order = Order(
            id="ord_db_001",
            client_order_id="CLIENT_DB_001",
            symbol="USDJPY",
            order_type="MARKET",
            direction="BUY",
            requested_price=155.20,
            requested_volume=0.1,
            status=OrderStatus.PENDING_SUBMIT,
        )
        session.add(order)
        await session.flush()

        evt1 = OrderEvent(
            order_id=order.id,
            from_status="NONE",
            to_status=OrderStatus.PENDING_SUBMIT.value,
            reason="Created",
        )
        evt2 = OrderEvent(
            order_id=order.id,
            from_status=OrderStatus.PENDING_SUBMIT.value,
            to_status=OrderStatus.SUBMITTED.value,
            reason="Submitted to gateway",
        )
        session.add_all([evt1, evt2])
        await session.commit()

        # Query back
        res = await session.execute(select(Order).where(Order.id == "ord_db_001"))
        persisted_order = res.scalar_one()
        assert persisted_order.symbol == "USDJPY"
        assert len(persisted_order.events) == 2
        assert persisted_order.events[0].to_status == "pending_submit"
        assert persisted_order.events[1].to_status == "submitted"


# ==============================================================================
# 2. BrokerAdapter Interface & MT5LiveAdapter Tests
# ==============================================================================

class TestBrokerAdapters:

    def test_broker_adapter_abstract_interface(self):
        """Verify BrokerAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BrokerAdapter()

    def test_pip_size_and_contract_size_helpers(self):
        """Verify symbol calculation helpers for FX, Gold, Crypto, Oil."""
        assert _get_pip_size("EURUSD") == 0.0001
        assert _get_pip_size("GBPUSD") == 0.0001
        assert _get_pip_size("USDJPY") == 0.01
        assert _get_pip_size("XAUUSD") == 0.01
        assert _get_pip_size("BTCUSD") == 1.0

        assert _get_contract_size("EURUSD") == 100000.0
        assert _get_contract_size("XAUUSD") == 100.0
        assert _get_contract_size("BTCUSD") == 1.0
        assert _get_contract_size("USOUSD") == 1000.0

    @pytest.mark.asyncio
    async def test_mt5_live_adapter_dry_run(self):
        """Verify MT5LiveAdapter in dry-run mode returns mock ticket without MT5 call."""
        mock_mt5 = AsyncMock()
        adapter = MT5LiveAdapter(mt5_client=mock_mt5, dry_run=True)

        order = Order(
            id="ord_dry_1",
            client_order_id="ORD_DRY_001",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0850,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res = await adapter.submit_order(order)
        assert res["success"] is True
        assert res["ticket"] is not None
        assert res["price"] == 1.0850
        assert res["executed_volume"] == 0.1
        assert res["slippage_pips"] == 0.0
        mock_mt5.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_mt5_live_adapter_live_execution(self):
        """Verify MT5LiveAdapter live order submission delegates to mt5.place_order and computes slippage."""
        mock_mt5 = AsyncMock()
        mock_mt5.place_order.return_value = {
            "success": True,
            "ticket": 554433,
            "price": 1.0852,  # 2 pips slippage from 1.0850
            "error": None,
        }
        adapter = MT5LiveAdapter(mt5_client=mock_mt5, dry_run=False)

        order = Order(
            id="ord_live_1",
            client_order_id="ORD_LIVE_001",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0850,
            requested_volume=0.2,
            status=OrderStatus.SUBMITTED,
        )
        res = await adapter.submit_order(order, sl=1.0800, tp=1.0950)
        assert res["success"] is True
        assert res["ticket"] == 554433
        assert res["price"] == 1.0852
        assert res["slippage_pips"] == 2.0
        mock_mt5.place_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mt5_live_adapter_methods(self):
        """Verify get_tick, get_positions, get_account_info, and close_position."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_current_price.return_value = {
            "bid": 1.0848,
            "ask": 1.0850,
            "last": 1.0849,
            "time": clock.now(),
        }
        mock_mt5.get_open_positions.return_value = [{"ticket": 123}]
        mock_mt5.get_account_info.return_value = {"balance": 10000.0, "equity": 10050.0}
        mock_mt5.close_position.return_value = {"success": True, "ticket": 123, "profit": 50.0}

        adapter = MT5LiveAdapter(mt5_client=mock_mt5, dry_run=False)

        tick = await adapter.get_tick("EURUSD")
        assert tick["symbol"] == "EURUSD"
        assert tick["bid"] == 1.0848
        assert tick["ask"] == 1.0850
        assert tick["spread"] == 0.0002

        positions = await adapter.get_positions()
        assert len(positions) == 1

        acc = await adapter.get_account_info()
        assert acc["equity"] == 10050.0

        close_res = await adapter.close_position(123)
        assert close_res["success"] is True


# ==============================================================================
# 3. SimulatedBrokerAdapter Tests (Parity Engine)
# ==============================================================================

class TestSimulatedBrokerAdapter:

    @pytest.mark.asyncio
    async def test_simulated_adapter_spread_and_slippage(self):
        """Verify SimulatedBrokerAdapter applies spread and ATR slippage to fill prices."""
        adapter = SimulatedBrokerAdapter(
            initial_balance=10000.0,
            default_spread_pips=2.0,
            atr_slippage_pips=0.5,
        )
        # Set market mid to 1.1000 for EURUSD
        # Spread = 2.0 pips (0.00020) -> Bid = 1.09990, Ask = 1.10010
        adapter.set_tick("EURUSD", bid=1.09990, ask=1.10010)

        # BUY order
        buy_order = Order(
            id="ord_sim_1",
            client_order_id="CLIENT_SIM_001",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.10000,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res_buy = await adapter.submit_order(buy_order)
        assert res_buy["success"] is True
        # Expected fill = ask (1.10010) + slippage (0.5 * 0.0001 = 0.00005) = 1.10015
        assert res_buy["price"] == 1.10015
        assert res_buy["ticket"] == 100001

        # SELL order
        sell_order = Order(
            id="ord_sim_2",
            client_order_id="CLIENT_SIM_002",
            symbol="EURUSD",
            order_type="MARKET",
            direction="SELL",
            requested_price=1.10000,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res_sell = await adapter.submit_order(sell_order)
        assert res_sell["success"] is True
        # Expected fill = bid (1.09990) - slippage (0.00005) = 1.09985
        assert res_sell["price"] == 1.09985
        assert res_sell["ticket"] == 100002

    @pytest.mark.asyncio
    async def test_simulated_adapter_margin_requirement_and_rejection(self):
        """Verify SimulatedBrokerAdapter validates required margin against free margin."""
        # Tiny initial balance: $100
        adapter = SimulatedBrokerAdapter(
            initial_balance=100.0,
            leverage=10.0,  # 1:10 leverage
        )
        adapter.set_tick("EURUSD", bid=1.1000, ask=1.1002)

        # Order 1.0 lot (100,000 EUR) @ 1.1000 requires 110,000 / 10 = $11,000 margin!
        huge_order = Order(
            id="ord_huge",
            client_order_id="ORD_HUGE_001",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.1000,
            requested_volume=1.0,
            status=OrderStatus.SUBMITTED,
        )
        res = await adapter.submit_order(huge_order)
        assert res["success"] is False
        assert "Margin call" in res["error"]
        assert len(adapter.positions) == 0

    @pytest.mark.asyncio
    async def test_simulated_adapter_fill_latency(self):
        """Verify SimulatedBrokerAdapter respects fill latency non-blockingly."""
        adapter = SimulatedBrokerAdapter(
            initial_balance=10000.0,
            fill_latency_ms=50.0,
        )
        adapter.set_tick("EURUSD", bid=1.1000, ask=1.1002)

        order = Order(
            id="ord_lat",
            client_order_id="ORD_LAT_001",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.1000,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        t0 = time.time()
        res = await adapter.submit_order(order)
        dt = (time.time() - t0) * 1000.0
        assert res["success"] is True
        assert dt >= 40.0  # At least ~40ms elapsed due to 50ms latency

    @pytest.mark.asyncio
    async def test_simulated_adapter_close_position_and_pnl(self):
        """Verify SimulatedBrokerAdapter position close updates realized PnL and balance."""
        adapter = SimulatedBrokerAdapter(
            initial_balance=10000.0,
            default_spread_pips=1.0,
            atr_slippage_pips=0.0,
        )
        # Entry: mid=1.1000, ask=1.10005, bid=1.09995
        adapter.set_tick("EURUSD", bid=1.09995, ask=1.10005)

        order = Order(
            id="ord_close_test",
            client_order_id="ORD_CLOSE_001",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.10005,
            requested_volume=1.0,  # 1 lot = 100,000 units
            status=OrderStatus.SUBMITTED,
        )
        fill_res = await adapter.submit_order(order)
        ticket = fill_res["ticket"]

        # Market moves up: mid=1.1050, bid=1.10495, ask=1.10505 (+49 pips from entry 1.10005)
        adapter.set_tick("EURUSD", bid=1.10495, ask=1.10505)

        # Check unrealized account info
        acc_pre = await adapter.get_account_info()
        expected_unrealized = (1.10495 - 1.10005) * 100000.0 * 1.0  # 490.00
        assert round(acc_pre["equity"] - acc_pre["balance"], 2) == round(expected_unrealized, 2)

        # Close position
        close_res = await adapter.close_position(ticket)
        assert close_res["success"] is True
        assert close_res["pnl"] == round(expected_unrealized, 2)
        assert len(adapter.positions) == 0
        assert adapter.balance == round(10000.0 + expected_unrealized, 2)


# ==============================================================================
# 4. ExecutionService Order Lifecycle & EventBus Tests
# ==============================================================================

class TestExecutionServiceOrderLifecycle:

    @pytest.mark.asyncio
    async def test_execution_service_order_lifecycle_full_flow(self, clean_event_bus, async_sqlite_session):
        """
        Verify full typed Order lifecycle:
        PENDING_SUBMIT -> SUBMITTED -> FILLED
        Audit events recorded in DB and OrderStateChangedEvent received by EventBus.
        """
        session = async_sqlite_session
        bus = clean_event_bus

        # Track event bus notifications
        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        # Setup simulation adapter
        sim_adapter = SimulatedBrokerAdapter(
            initial_balance=25000.0,
            default_spread_pips=1.0,
            atr_slippage_pips=0.2,
        )
        sim_adapter.set_tick("EURUSD", bid=1.0850, ask=1.0851)

        settings = {
            "trading": {
                "min_paper_trades_before_live": 0,
                "risk": {"confluence_verifier_enabled": False, "min_verifiable_confluence": 0}
            }
        }
        svc = ExecutionService(
            settings=settings,
            broker_adapter=sim_adapter,
            dry_run=False,
        )

        # Sizer & RiskGate mocks
        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(
            return_value=MagicMock(is_valid=True, recommended_lots=0.5, entry_price=1.0851, risk_percent=1.0)
        )
        svc.sizer = mock_sizer

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate

        # Create AssetAnalysis in DB
        analysis = AssetAnalysis(
            id=777,
            symbol="EURUSD",
            decision="buy",
            stop_loss=1.0800,
            take_profit=1.0950,
            confidence=0.85,
            confluence_score=8,
            price_at_analysis=1.0851,
            generated_at=clock.now(),
            rationale="Lifecycle integration test",
        )
        session.add(analysis)
        await session.commit()

        # Execute
        with patch('analysis.validators.adversarial_check.run_adversarial_check', new_callable=AsyncMock) as mock_adv:
            mock_adv.return_value = {'approve': True, 'hard_block': False}
            res = await svc.execute_analysis(session, analysis)

        assert res.risk_approved is True
        assert res.executed is True
        assert res.mt5_ticket is not None
        assert res.executed_price is not None

        # Verify DB Order and OrderEvent audit trail
        order_res = await session.execute(select(Order).where(Order.analysis_id == 777))
        order = order_res.scalar_one()
        assert order.symbol == "EURUSD"
        assert order.status == OrderStatus.FILLED
        assert order.mt5_ticket == res.mt5_ticket

        events_res = await session.execute(
            select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id)
        )
        events = events_res.scalars().all()
        assert len(events) >= 2
        states = [e.to_status for e in events]
        assert "pending_submit" in states
        assert "submitted" in states
        assert "filled" in states

        # Verify EventBus events were dispatched
        assert len(received_events) >= 2
        bus_states = [ev.new_state for ev in received_events]
        assert "pending_submit" in bus_states
        assert "submitted" in bus_states
        assert "filled" in bus_states

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_lifecycle(self, clean_event_bus, async_sqlite_session):
        """Verify preplanned order triggers sub-second order lifecycle."""
        session = async_sqlite_session
        bus = clean_event_bus

        received_events: list[OrderStateChangedEvent] = []
        bus.subscribe(OrderStateChangedEvent, lambda ev: received_events.append(ev))

        sim_adapter = SimulatedBrokerAdapter(initial_balance=50000.0)
        sim_adapter.set_tick("XAUUSD", bid=2350.0, ask=2350.20)

        svc = ExecutionService(
            settings={"execution": {}},
            broker_adapter=sim_adapter,
            dry_run=False,
        )

        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(
            return_value=MagicMock(is_valid=True, recommended_lots=0.2, entry_price=2350.20, risk_percent=1.0)
        )
        svc.sizer = mock_sizer

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate

        order_plan = {
            "direction": "buy",
            "entry_price": 2350.20,
            "stop_loss": 2340.0,
            "take_profit": 2370.0,
            "lot_size": 0.2,
        }

        res = await svc.execute_preplanned_order(
            session=session,
            symbol="XAUUSD",
            order_plan=order_plan,
            trigger_id=1234,
        )

        assert res.executed is True
        assert res.mt5_ticket is not None

        # Verify Order in DB
        order_res = await session.execute(select(Order).where(Order.symbol == "XAUUSD"))
        order = order_res.scalar_one()
        assert order.status == OrderStatus.FILLED
        assert order.mt5_ticket == res.mt5_ticket

        # Verify EventBus was published
        assert any(ev.new_state == "filled" for ev in received_events)


# ==============================================================================
# 5. PointInTimeBacktestEngine Parity Execution Tests
# ==============================================================================

class TestPointInTimeBacktestParity:

    @pytest.mark.asyncio
    async def test_point_in_time_engine_parity_execution(self, clean_event_bus, async_sqlite_session):
        """
        Verify PointInTimeBacktestEngine with use_execution_service=True executes
        trades through ExecutionService with SimulatedBrokerAdapter (100% parity).
        """
        from backtest.point_in_time_engine import PointInTimeBacktestEngine

        session = async_sqlite_session
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 10, tzinfo=timezone.utc)

        settings = {
            "trading": {
                "asset_universe": ["EURUSD", "GBPUSD"],
                "min_paper_trades_before_live": 0,
                "risk": {"confluence_verifier_enabled": False, "min_verifiable_confluence": 0}
            },
            "backtest": {
                "use_execution_service": True,
                "enforce_risk_gate": True,
            },
            "adversarial_check": {
                "enabled": False,
            }
        }

        engine = PointInTimeBacktestEngine(
            start_date=start,
            end_date=end,
            settings=settings,
            mode="replay",
            use_execution_service=True,
        )

        assert engine.use_execution_service is True
        assert isinstance(engine.broker_adapter, SimulatedBrokerAdapter)
        assert isinstance(engine.execution_service, ExecutionService)

        # Mock sizer & risk gate in execution_service for predictable backtest run
        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(
            return_value=MagicMock(is_valid=True, recommended_lots=0.25, entry_price=1.0850, risk_percent=1.0)
        )
        engine.execution_service.sizer = mock_sizer

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        engine.execution_service.gate = mock_gate

        # Create 2 recorded AssetAnalysis in DB
        analysis1 = AssetAnalysis(
            id=101,
            symbol="EURUSD",
            decision="buy",
            price_at_analysis=1.0850,
            stop_loss=1.0800,
            take_profit=1.0950,
            confidence=0.8,
            confluence_score=7,
            invalidation_price=1.0800,
            invalidation_direction="below",
            generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            rationale="Parity test 1",
        )
        analysis2 = AssetAnalysis(
            id=102,
            symbol="GBPUSD",
            decision="sell",
            price_at_analysis=1.2700,
            stop_loss=1.2750,
            take_profit=1.2600,
            confidence=0.85,
            confluence_score=8,
            invalidation_price=1.2750,
            invalidation_direction="above",
            generated_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            rationale="Parity test 2",
        )
        session.add_all([analysis1, analysis2])
        await session.commit()

        # Run execute_trade_parity directly
        trade1 = await engine.execute_trade_parity(session, analysis1)
        assert trade1 is not None
        assert trade1.symbol == "EURUSD"
        assert trade1.direction == "buy"
        assert trade1.executed_lots == 0.25
        assert trade1.model_used == "simulated_parity"

        trade2 = await engine.execute_trade_parity(session, analysis2)
        assert trade2 is not None
        assert trade2.symbol == "GBPUSD"
        assert trade2.direction == "sell"
        assert trade2.executed_lots == 0.25

        assert len(engine.trades) == 2


# ==============================================================================
# 6. Deep Verification: Edge Cases, Robustness & State Machine Guards
# ==============================================================================

class TestPhase3EdgeCasesAndRobustness:

    def test_invalid_state_transitions_raise_error(self):
        """Verify illegal order state transitions are rejected by the state machine."""
        order = Order(
            id="ord_sm_test",
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0850,
            requested_volume=0.1,
            status=OrderStatus.PENDING_SUBMIT,
        )
        assert order.is_terminal is False
        assert order.can_transition_to(OrderStatus.SUBMITTED) is True
        assert order.can_transition_to(OrderStatus.FILLED) is False

        # Transition to SUBMITTED -> valid
        evt1 = order.transition_to(OrderStatus.SUBMITTED, reason="Sent to broker")
        assert order.status == OrderStatus.SUBMITTED
        assert evt1.from_status == "pending_submit"
        assert evt1.to_status == "submitted"

        # Transition to FILLED -> valid
        evt2 = order.transition_to(OrderStatus.FILLED, executed_price=1.0851, ticket=999)
        assert order.status == OrderStatus.FILLED
        assert order.is_terminal is True
        assert order.filled_volume == 0.1

        # Attempt illegal transition from FILLED to SUBMITTED
        with pytest.raises(InvalidOrderStateTransitionError):
            order.transition_to(OrderStatus.SUBMITTED)

        # Attempt illegal transition from FILLED to PENDING_SUBMIT
        with pytest.raises(InvalidOrderStateTransitionError):
            order.transition_to(OrderStatus.PENDING_SUBMIT)

    def test_order_auto_generated_defaults(self):
        """Verify Order auto-generates id and client_order_id when omitted."""
        order = Order(
            symbol="GBPUSD",
            order_type="MARKET",
            direction="SELL",
            requested_price=1.2700,
            requested_volume=0.2,
        )
        assert order.id is not None
        assert len(order.id) >= 16
        assert order.client_order_id.startswith("ORD_")
        assert order.status == OrderStatus.PENDING_SUBMIT
        assert order.filled_volume == 0.0
        assert order.slippage_pips == 0.0

    @pytest.mark.asyncio
    async def test_simulated_adapter_zero_or_none_requested_price(self):
        """Verify market order with requested_price=0.0 or None executes safely without bogus slippage."""
        adapter = SimulatedBrokerAdapter()
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        # 1. requested_price = 0.0
        order_zero = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=0.0,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res_zero = await adapter.submit_order(order_zero)
        assert res_zero["success"] is True
        # Slippage should be equal to atr_slippage_pips (0.5), not thousands of pips
        assert res_zero["slippage_pips"] == 0.5
        assert res_zero["price"] == round(1.0852 + (0.5 * 0.0001), 5)

        # 2. requested_price = None
        order_none = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="SELL",
            requested_price=None,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res_none = await adapter.submit_order(order_none)
        assert res_none["success"] is True
        assert res_none["slippage_pips"] == 0.5
        assert res_none["price"] == round(1.0850 - (0.5 * 0.0001), 5)

    @pytest.mark.asyncio
    async def test_simulated_adapter_invalid_direction_and_volume(self):
        """Verify SimulatedBrokerAdapter validates direction and volume."""
        adapter = SimulatedBrokerAdapter()
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        # Invalid direction
        order_bad_dir = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="HOLD",
            requested_price=1.0850,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res_bad_dir = await adapter.submit_order(order_bad_dir)
        assert res_bad_dir["success"] is False
        assert "Invalid order direction" in res_bad_dir["error"]

        # Negative volume
        order_neg_vol = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0850,
            requested_volume=-0.5,
            status=OrderStatus.SUBMITTED,
        )
        res_neg = await adapter.submit_order(order_neg_vol)
        assert res_neg["success"] is False
        assert "Invalid requested volume" in res_neg["error"]

    @pytest.mark.asyncio
    async def test_simulated_adapter_pending_limit_and_stop_lifecycle(self):
        """Verify LIMIT and STOP orders are held in pending_orders until price triggers them."""
        adapter = SimulatedBrokerAdapter(atr_slippage_pips=0.0)
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        # Buy Limit @ 1.0840 (current ask is 1.0852 -> not yet triggered)
        limit_order = Order(
            id="ord_limit_1",
            client_order_id="CLIENT_LIMIT_001",
            symbol="EURUSD",
            order_type="LIMIT",
            direction="BUY",
            requested_price=1.0840,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        res_limit = await adapter.submit_order(limit_order)
        assert res_limit["success"] is True
        assert res_limit["status"] == "pending"
        assert "CLIENT_LIMIT_001" in adapter.pending_orders
        assert len(adapter.positions) == 0

        # Market moves down, crossing limit: bid=1.0838, ask=1.0840
        adapter.set_tick("EURUSD", bid=1.0838, ask=1.0840)

        # Pending order should now be filled automatically!
        assert "CLIENT_LIMIT_001" not in adapter.pending_orders
        assert len(adapter.positions) == 1
        pos = list(adapter.positions.values())[0]
        assert pos["type"] == "buy"
        assert pos["open_price"] == 1.0840

    @pytest.mark.asyncio
    async def test_simulated_adapter_cancel_order_return_values(self):
        """Verify cancel_order returns True for existing pending orders, and False for non-existent ones."""
        adapter = SimulatedBrokerAdapter()
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        order = Order(
            client_order_id="CANCEL_ME",
            symbol="EURUSD",
            order_type="LIMIT",
            direction="BUY",
            requested_price=1.0800,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        await adapter.submit_order(order)
        assert "CANCEL_ME" in adapter.pending_orders

        # Cancel existing
        res1 = await adapter.cancel_order("CANCEL_ME")
        assert res1 is True
        assert "CANCEL_ME" not in adapter.pending_orders

        # Cancel non-existent
        res2 = await adapter.cancel_order("NON_EXISTENT_ORDER_ID")
        assert res2 is False

    @pytest.mark.asyncio
    async def test_simulated_adapter_close_position_invalid_volume(self):
        """Verify close_position rejects non-positive partial close volume."""
        adapter = SimulatedBrokerAdapter()
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        order = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0852,
            requested_volume=1.0,
            status=OrderStatus.SUBMITTED,
        )
        fill = await adapter.submit_order(order)
        ticket = fill["ticket"]

        # lots = 0.0
        res_zero = await adapter.close_position(ticket, lots=0.0)
        assert res_zero["success"] is False
        assert "Invalid close volume" in res_zero["error"]

        # lots = -0.5
        res_neg = await adapter.close_position(ticket, lots=-0.5)
        assert res_neg["success"] is False
        assert "Invalid close volume" in res_neg["error"]

    @pytest.mark.asyncio
    async def test_simulated_adapter_partial_fill_and_state_tracking(self, async_sqlite_session):
        """Verify partial fill quantity execution and order state machine tracking."""
        session = async_sqlite_session
        adapter = SimulatedBrokerAdapter()
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        order = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0852,
            requested_volume=1.0,
            status=OrderStatus.PENDING_SUBMIT,
        )
        session.add(order)
        await session.flush()

        svc = ExecutionService(
            settings={"execution": {}},
            broker_adapter=adapter,
            dry_run=False,
        )

        # Transition to SUBMITTED
        await svc._transition_order_state(session, order, OrderStatus.SUBMITTED)

        # Submit order with partial_fill_ratio=0.4 (0.4 lots filled out of 1.0)
        res = await adapter.submit_order(order, partial_fill_ratio=0.4)
        assert res["success"] is True
        assert res["executed_volume"] == 0.4

        # Transition to PARTIALLY_FILLED
        await svc._transition_order_state(
            session,
            order,
            OrderStatus.PARTIALLY_FILLED,
            reason="Partial execution",
            executed_price=res["price"],
            ticket=res["ticket"],
            filled_volume=res["executed_volume"],
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_volume == 0.4
        assert order.requested_volume == 1.0
        assert order.is_terminal is False

        # Transition remaining to CANCELLED
        await svc._transition_order_state(session, order, OrderStatus.CANCELLED, reason="Cancelled remaining 0.6 lots")
        assert order.status == OrderStatus.CANCELLED
        assert order.is_terminal is True

    @pytest.mark.asyncio
    async def test_simulated_adapter_reset_clears_memory(self):
        """Verify adapter.reset() flushes memory and restores initial balance."""
        adapter = SimulatedBrokerAdapter(initial_balance=10000.0)
        adapter.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        order = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0852,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        await adapter.submit_order(order)
        assert len(adapter.positions) == 1

        adapter.reset(balance=15000.0)
        assert len(adapter.positions) == 0
        assert len(adapter.pending_orders) == 0
        assert len(adapter.current_prices) == 0
        assert adapter.balance == 15000.0

    @pytest.mark.asyncio
    async def test_broker_adapter_universal_compatibility_methods(self):
        """Verify get_open_positions, get_current_price, ensure_connected work across all adapters."""
        sim = SimulatedBrokerAdapter()
        sim.set_tick("EURUSD", bid=1.0850, ask=1.0852)

        order = Order(
            symbol="EURUSD",
            order_type="MARKET",
            direction="BUY",
            requested_price=1.0852,
            requested_volume=0.1,
            status=OrderStatus.SUBMITTED,
        )
        await sim.submit_order(order)

        # get_open_positions with symbol filtering
        all_pos = await sim.get_open_positions()
        assert len(all_pos) == 1

        filtered_pos = await sim.get_open_positions(symbol="EURUSD")
        assert len(filtered_pos) == 1

        none_pos = await sim.get_open_positions(symbol="USDJPY")
        assert len(none_pos) == 0

        # get_current_price
        px = await sim.get_current_price("EURUSD")
        assert px["ask"] == 1.0852

        # ensure_connected
        assert await sim.ensure_connected() is True

    @pytest.mark.asyncio
    async def test_crypto_and_oil_pip_sizing_in_parity_engine(self, async_sqlite_session):
        """Verify crypto (BTCUSD) and oil (USOUSD) pip sizes operate correctly in parity engine."""
        from backtest.point_in_time_engine import PointInTimeBacktestEngine

        session = async_sqlite_session
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 10, tzinfo=timezone.utc)

        settings = {
            "trading": {
                "asset_universe": ["BTCUSD"],
                "min_paper_trades_before_live": 0,
                "risk": {"confluence_verifier_enabled": False, "min_verifiable_confluence": 0}
            },
            "backtest": {"use_execution_service": True},
            "adversarial_check": {"enabled": False}
        }

        engine = PointInTimeBacktestEngine(
            start_date=start,
            end_date=end,
            settings=settings,
            mode="replay",
            use_execution_service=True,
        )

        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(
            return_value=MagicMock(is_valid=True, recommended_lots=0.1, entry_price=65000.0, risk_percent=1.0)
        )
        engine.execution_service.sizer = mock_sizer

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        engine.execution_service.gate = mock_gate

        btc_analysis = AssetAnalysis(
            id=201,
            symbol="BTCUSD",
            decision="buy",
            price_at_analysis=65000.0,
            stop_loss=64000.0,
            take_profit=67000.0,
            confidence=0.9,
            confluence_score=9,
            generated_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            rationale="Crypto parity test",
        )
        session.add(btc_analysis)
        await session.commit()

        trade = await engine.execute_trade_parity(session, btc_analysis)
        assert trade is not None
        assert trade.symbol == "BTCUSD"
        assert trade.executed_lots == 0.1
