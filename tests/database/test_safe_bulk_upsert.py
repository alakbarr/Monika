"""
Unit test suite for safe_bulk_upsert and safe_expunge_all.
Tests cross-dialect bulk upsert, chunking, conflict resolution, and identity map hygiene.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from monika.infrastructure.database.models import Base, TechnicalIndicator
from monika.infrastructure.database.safe_ops import safe_bulk_upsert, safe_expunge_all


@pytest.mark.asyncio
async def test_safe_bulk_upsert_insert_and_conflict_update(tmp_path):
    """Verify safe_bulk_upsert inserts new records and updates conflicting records cleanly."""
    db_path = tmp_path / "test_bulk_upsert.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    now = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    rows_initial = [
        {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "timestamp": now,
            "indicator_name": "RSI_14",
            "value_json": '{"value": 55.4}',
        },
        {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "timestamp": now,
            "indicator_name": "EMA_20",
            "value_json": '{"value": 1.0850}',
        },
    ]

    async with sm() as session:
        # 1. Initial bulk insert
        saved = await safe_bulk_upsert(
            session=session,
            model=TechnicalIndicator,
            rows=rows_initial,
            index_elements=["symbol", "timeframe", "timestamp", "indicator_name"],
            update_cols=["value_json"],
            chunk_size=1,  # Force chunking
        )
        assert saved == 2
        await session.commit()
        await safe_expunge_all(session)

        # Invariant: Core execution must not populate ORM identity map
        assert len(session.identity_map) == 0

        # Query back and check values
        records = (await session.execute(select(TechnicalIndicator))).scalars().all()
        assert len(records) == 2

    # 2. Update with conflict on existing keys
    rows_update = [
        {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "timestamp": now,
            "indicator_name": "RSI_14",
            "value_json": '{"value": 62.1}',  # Updated value
        },
        {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "timestamp": now,
            "indicator_name": "SMA_50",
            "value_json": '{"value": 1.0820}',  # New indicator
        },
    ]

    async with sm() as session:
        saved_update = await safe_bulk_upsert(
            session=session,
            model=TechnicalIndicator,
            rows=rows_update,
            index_elements=["symbol", "timeframe", "timestamp", "indicator_name"],
            update_cols=["value_json"],
            chunk_size=500,
        )
        assert saved_update == 2
        await session.commit()
        await safe_expunge_all(session)

        # Query back
        all_indicators = (
            (await session.execute(select(TechnicalIndicator).order_by(TechnicalIndicator.indicator_name.asc())))
            .scalars()
            .all()
        )
        assert len(all_indicators) == 3
        ind_map = {r.indicator_name: r.value_json for r in all_indicators}
        assert ind_map["EMA_20"] == '{"value": 1.0850}'
        assert ind_map["RSI_14"] == '{"value": 62.1}'  # Updated via ON CONFLICT
        assert ind_map["SMA_50"] == '{"value": 1.0820}'


@pytest.mark.asyncio
async def test_safe_bulk_upsert_empty_rows(tmp_path):
    """Verify safe_bulk_upsert returns 0 immediately when given empty rows."""
    db_path = tmp_path / "test_bulk_empty.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with sm() as session:
        saved = await safe_bulk_upsert(
            session=session,
            model=TechnicalIndicator,
            rows=[],
            index_elements=["symbol", "timeframe", "timestamp", "indicator_name"],
        )
        assert saved == 0
