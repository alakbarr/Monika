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


@pytest.mark.asyncio
async def test_unit_of_work_and_ports_compliance(async_session: AsyncSession):
    from monika.domain.ports import (
        ActivityLogRepositoryPort,
        PositionRepositoryPort,
        SystemConfigRepositoryPort,
        TradeProposalRepositoryPort,
        UnitOfWorkPort,
    )
    from monika.infrastructure.database.repositories import SqlAlchemyUnitOfWork

    uow = SqlAlchemyUnitOfWork(session=async_session)
    assert isinstance(uow, UnitOfWorkPort)
    assert isinstance(uow.positions, PositionRepositoryPort)
    assert isinstance(uow.trade_proposals, TradeProposalRepositoryPort)
    assert isinstance(uow.system_config, SystemConfigRepositoryPort)
    assert isinstance(uow.activity_logs, ActivityLogRepositoryPort)

    async with uow:
        # Create position through uow
        pos = await uow.positions.create_position(
            symbol="GBPUSD",
            direction="SELL",
            volume=0.2,
            entry_price=1.2500,
            mt5_ticket=2002,
        )
        assert pos.mt5_ticket == 2002
        await uow.system_config.set("uow_test_key", "verified")
        await uow.commit()

    # Verify persisted
    assert await uow.positions.count_open_positions() == 1
    assert await uow.system_config.get("uow_test_key") == "verified"


@pytest.mark.asyncio
async def test_paper_trade_repository_lifecycle(async_session: AsyncSession):
    from monika.infrastructure.database.repositories.paper_trade_repository import SqlAlchemyPaperTradeRepository

    repo = SqlAlchemyPaperTradeRepository(async_session)

    # Initial open records
    assert len(await repo.get_open_records()) == 0

    # Create paper trade
    record = await repo.create_record(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        risk_pct=1.0,
    )
    assert record.id is not None
    assert record.status == "open"

    # Fetch open
    open_recs = await repo.get_open_records("EURUSD")
    assert len(open_recs) == 1
    assert open_recs[0].id == record.id

    # Close paper trade
    closed = await repo.close_record(record.id, exit_price=1.0900, pnl_pct=0.46)
    assert closed is not None
    assert closed.status == "closed"
    assert closed.pnl_pct == 0.46
    assert len(await repo.get_open_records()) == 0


@pytest.mark.asyncio
async def test_asset_analysis_repository_lifecycle(async_session: AsyncSession):
    from monika.infrastructure.database.domain_models.analysis import AssetAnalysis
    from monika.infrastructure.database.repositories.asset_analysis_repository import SqlAlchemyAssetAnalysisRepository

    repo = SqlAlchemyAssetAnalysisRepository(async_session)

    # Insert test analysis
    analysis = AssetAnalysis(
        symbol="GBPUSD",
        confidence=0.85,
        confluence_score=85,
        decision="EXECUTE",
    )
    async_session.add(analysis)
    await async_session.flush()

    fetched = await repo.get_by_id(analysis.id)
    assert fetched is not None
    assert fetched.symbol == "GBPUSD"
    assert fetched.confidence == 0.85

    latest = await repo.get_latest_by_symbol("GBPUSD")
    assert latest is not None
    assert latest.id == analysis.id


@pytest.mark.asyncio
async def test_market_data_repository_lifecycle(async_session: AsyncSession):
    from datetime import UTC, datetime
    from monika.infrastructure.database.domain_models.market import PriceOHLCV, VIXData, TreasuryYield
    from monika.infrastructure.database.repositories.market_data_repository import SqlAlchemyMarketDataRepository

    repo = SqlAlchemyMarketDataRepository(async_session)

    now = datetime.now(UTC)
    async_session.add(
        PriceOHLCV(
            symbol="EURUSD", timeframe="H1", timestamp=now, open=1.08, high=1.09, low=1.07, close=1.085, volume=100.0
        )
    )
    async_session.add(VIXData(date=now, close=15.2))
    async_session.add(TreasuryYield(date=now, tenor="10Y", yield_percent=4.25))
    await async_session.flush()

    bars = await repo.get_recent_bars("EURUSD", "H1", limit=10)
    assert len(bars) == 1
    assert bars[0].close == 1.085

    vix = await repo.get_latest_vix()
    assert vix == 15.2

    y10 = await repo.get_latest_yield("10Y")
    assert y10 == 4.25


@pytest.mark.asyncio
async def test_unit_of_work_reentrancy_and_nested_savepoint(async_session: AsyncSession):
    from monika.infrastructure.database.repositories import SqlAlchemyUnitOfWork

    uow = SqlAlchemyUnitOfWork(session=async_session)

    # First entry
    async with uow:
        pos1 = await uow.positions.create_position(
            symbol="AUDUSD", direction="BUY", volume=0.1, entry_price=0.6500, mt5_ticket=3001
        )
        assert pos1.mt5_ticket == 3001

        # Test nested savepoint rollback
        try:
            async with uow.nested():
                await uow.positions.create_position(
                    symbol="NZDUSD", direction="BUY", volume=0.1, entry_price=0.6000, mt5_ticket=3002
                )
                raise ValueError("Force rollback of inner nested savepoint")
        except ValueError:
            pass

        await uow.commit()

    # Outer position 3001 must exist, inner 3002 must have been rolled back
    assert await uow.positions.get_by_ticket(3001) is not None
    assert await uow.positions.get_by_ticket(3002) is None


@pytest.mark.asyncio
async def test_position_paper_vs_live_no_collision(async_session: AsyncSession):
    from monika.infrastructure.database.repositories import PositionRepository

    repo = PositionRepository(async_session)

    # 1. Create open live position on EURUSD
    live_pos = await repo.create_position(
        symbol="EURUSD", direction="BUY", volume=1.0, entry_price=1.0850, mt5_ticket=5001, is_paper=False
    )
    assert live_pos.is_paper is False

    # 2. Create open paper position on EURUSD (must succeed without IntegrityError!)
    paper_pos = await repo.create_position(
        symbol="EURUSD", direction="BUY", volume=0.5, entry_price=1.0850, mt5_ticket=5002, is_paper=True
    )
    assert paper_pos.is_paper is True

    # Both open positions must exist simultaneously
    open_live = await repo.get_open_positions(symbol="EURUSD", is_paper=False)
    open_paper = await repo.get_open_positions(symbol="EURUSD", is_paper=True)
    assert len(open_live) == 1
    assert len(open_paper) == 1
