import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.models import Base, Order, OrderStatus, AssetAnalysis
from risk.position_sizing import SizingResult
from execution.service.state_machine import OrderStateMachine
from execution.service.order_creator import OrderCreator
from execution.service.sizing_calculator import SizingCalculator
from execution.service.audit_logger import TradeAuditLogger
from execution.service.reconciliation import ReconciliationHelper


@pytest.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_order_creator_and_validation():
    # Test valid order creation
    order = OrderCreator.create_order(
        symbol="EURUSD",
        order_type="LIMIT",
        direction="BUY",
        requested_price=1.0850,
        requested_volume=0.2,
        analysis_id=55,
    )
    assert order.symbol == "EURUSD"
    assert order.order_type == "LIMIT"
    assert order.direction == "BUY"
    assert order.requested_price == 1.0850
    assert order.requested_volume == 0.2
    assert order.status == OrderStatus.PENDING_SUBMIT

    # Test validations
    valid, err = OrderCreator.validate_order_parameters("EURUSD", "BUY", 1.0850, sl=1.0800, tp=1.0950)
    assert valid is True
    assert err is None

    # Invalid BUY SL (SL >= entry)
    valid, err = OrderCreator.validate_order_parameters("EURUSD", "BUY", 1.0850, sl=1.0900, tp=1.0950)
    assert valid is False
    assert "Invalid BUY SL" in err

    # Invalid SELL TP (TP >= entry)
    valid, err = OrderCreator.validate_order_parameters("EURUSD", "SELL", 1.0850, sl=1.0900, tp=1.0890)
    assert valid is False
    assert "Invalid SELL TP" in err


@pytest.mark.asyncio
async def test_sizing_calculator():
    # Test price drift validation
    valid, drift = SizingCalculator.validate_price_drift(
        current_market_price=2005.0,
        reference_price=2000.0,
        max_drift_pct=1.0,
    )
    assert valid is True
    assert abs(drift - 0.25) < 1e-4

    # Large drift
    valid, drift = SizingCalculator.validate_price_drift(
        current_market_price=2030.0,
        reference_price=2000.0,
        max_drift_pct=1.0,
    )
    assert valid is False
    assert drift == 1.5

    # Test slippage computation
    slippage = SizingCalculator.compute_slippage_pips(expected_price=1.08500, executed_price=1.08515, point_size=0.0001)
    assert slippage == 1.5


@pytest.mark.asyncio
async def test_state_machine_transition(async_session):
    order = OrderCreator.create_order(
        symbol="GBPUSD",
        order_type="MARKET",
        direction="SELL",
        requested_price=1.2650,
        requested_volume=0.5,
    )
    async_session.add(order)
    await async_session.flush()

    # Transition to SUBMITTED
    evt1 = await OrderStateMachine.transition_order_state(
        session=async_session,
        order=order,
        new_status=OrderStatus.SUBMITTED,
        reason="Order sent to broker",
    )
    assert order.status == OrderStatus.SUBMITTED
    assert evt1.from_status == OrderStatus.PENDING_SUBMIT
    assert evt1.to_status == OrderStatus.SUBMITTED

    # Transition to FILLED
    evt2 = await OrderStateMachine.transition_order_state(
        session=async_session,
        order=order,
        new_status=OrderStatus.FILLED,
        reason="Order filled by MT5",
        executed_price=1.2648,
        ticket=123456,
        filled_volume=0.5,
    )
    assert order.status == OrderStatus.FILLED
    assert order.mt5_ticket == 123456
    assert evt2.to_status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_trade_audit_logger_and_reconciliation(async_session):
    analysis = AssetAnalysis(
        id=777,
        symbol="USDJPY",
        decision="buy",
        confidence=0.85,
        stop_loss=150.00,
        take_profit=155.00,
        generated_at=datetime.now(timezone.utc),
    )
    async_session.add(analysis)
    await async_session.flush()

    sizing = MagicMock()
    sizing.recommended_lots = 0.2
    sizing.entry_price = 152.00
    mt5_res = {"success": True, "ticket": 998877, "price": 152.05}

    pos_id = await TradeAuditLogger.save_position(
        session=async_session,
        analysis=analysis,
        sizing=sizing,
        mt5_result=mt5_res,
        dry_run=True,
    )
    assert pos_id is not None

    # Test audit log
    await TradeAuditLogger.log_result(
        session=async_session,
        summary_text="EXECUTED USDJPY BUY",
        analysis_id=777,
    )

    # Test reconciliation helper restoring executed IDs
    cache_dict = {}
    restored = await ReconciliationHelper.restore_executed_ids_from_db(async_session, cache_dict)
    assert restored >= 1
    assert 777 in cache_dict
