import json
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from monika.infrastructure.database.models import Base
from monika.infrastructure.database.repositories import (
    PositionRepository,
    ActivityLogRepository,
    SystemConfigRepository,
    TradeProposalRepository,
)


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_position_repository_lifecycle(async_session: AsyncSession):
    repo = PositionRepository(async_session)

    # Initial open count should be 0
    assert await repo.count_open_positions() == 0

    # Create a position
    pos = await repo.create_position(
        symbol="EURUSD",
        direction="BUY",
        volume=0.1,
        entry_price=1.0850,
        mt5_ticket=1001,
    )
    assert pos.mt5_ticket == 1001
    assert pos.status == "open"

    # Count and retrieve open positions
    assert await repo.count_open_positions() == 1
    open_positions = await repo.get_open_positions()
    assert len(open_positions) == 1
    assert open_positions[0].mt5_ticket == 1001

    # Get by ticket
    fetched = await repo.get_by_ticket(1001)
    assert fetched is not None
    assert fetched.symbol == "EURUSD"

    # Get by tickets list
    by_tickets = await repo.get_by_tickets([1001, 9999])
    assert len(by_tickets) == 1
    assert by_tickets[0].mt5_ticket == 1001

    # Close position
    closed = await repo.close_position(1001, pnl=50.0)
    assert closed is not None
    assert closed.status == "closed"
    assert closed.pnl == 50.0

    # Open count should now be 0
    assert await repo.count_open_positions() == 0


@pytest.mark.asyncio
async def test_activity_log_repository(async_session: AsyncSession):
    repo = ActivityLogRepository(async_session)

    # Log activities
    await repo.log_activity("system", "Daemon started", actor="cli")
    await repo.log_activity("trade", "Order executed", actor="risk_gate", related_id=1001)
    await repo.log_activity("system", "Healthcheck OK", actor="watchdog")

    # Count by category
    assert await repo.count_by_category("system") == 2
    assert await repo.count_by_category("trade") == 1
    assert await repo.count_by_category("unknown") == 0

    # Retrieve recent
    recent_all = await repo.get_recent(limit=10)
    assert len(recent_all) == 3

    recent_trade = await repo.get_recent(limit=10, category="trade")
    assert len(recent_trade) == 1
    assert recent_trade[0].description == "Order executed"
    assert recent_trade[0].related_id == 1001


@pytest.mark.asyncio
async def test_system_config_repository(async_session: AsyncSession):
    repo = SystemConfigRepository(async_session)

    # Get unset key returns default
    assert await repo.get("non_existent", default="fallback") == "fallback"

    # Set and get key
    await repo.set("custom_key", "custom_val", description="Testing")
    assert await repo.get("custom_key") == "custom_val"

    # Kill switch lifecycle
    assert await repo.is_kill_switch_active() is False
    await repo.set_kill_switch(True)
    assert await repo.is_kill_switch_active() is True
    await repo.set_kill_switch(False)
    assert await repo.is_kill_switch_active() is False

    # System paused lifecycle
    assert await repo.is_system_paused() is False
    await repo.set_system_paused(True)
    assert await repo.is_system_paused() is True
    await repo.set_system_paused(False)
    assert await repo.is_system_paused() is False

    # Risk overrides
    assert await repo.get_risk_override() is None
    override_payload = json.dumps({"risk_percent": 1.5, "max_dd": 5.0})
    await repo.set_risk_override(override_payload)
    override = await repo.get_risk_override()
    assert override == override_payload


@pytest.mark.asyncio
async def test_trade_proposal_repository(async_session: AsyncSession):
    repo = TradeProposalRepository(async_session)

    # Create trigger
    trigger = await repo.create_trigger(
        trigger_type="breakout",
        condition_json='{"price": 1.0850}',
    )
    assert trigger.id is not None
    assert trigger.status == "pending"

    # Get by id
    fetched = await repo.get_trigger_by_id(trigger.id)
    assert fetched is not None
    assert fetched.trigger_type == "breakout"

    # Update trigger status
    updated = await repo.update_trigger_status(trigger.id, status="fired")
    assert updated is not None
    assert updated.status == "fired"
    assert updated.fired_at is not None

    # Get recent triggers
    recent = await repo.get_recent_triggers(status="fired")
    assert len(recent) == 1
    assert recent[0].id == trigger.id
