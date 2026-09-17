import pytest
import pytest_asyncio
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database.models import Base, SystemConfig

@pytest_asyncio.fixture
async def test_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_system_config_upsert_insert_and_update(test_db_session):
    session = test_db_session
    
    # 1. First insert
    key = "test_key_1"
    item1 = await SystemConfig.upsert(session, key=key, value="value_1", description="desc 1")
    await session.commit()
    assert item1.key == key
    assert item1.value == "value_1"
    assert item1.description == "desc 1"
    
    # Verify in DB
    saved = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    assert saved is not None
    assert saved.value == "value_1"
    
    # 2. Second write with same key (update)
    item2 = await SystemConfig.upsert(session, key=key, value="value_2", description="desc 2")
    await session.commit()
    assert item2.key == key
    assert item2.value == "value_2"
    assert item2.description == "desc 2"
    
    # Verify count is still 1 and value is updated
    rows = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "value_2"

@pytest.mark.asyncio
async def test_context_drift_repeated_monitoring_writes(test_db_session):
    """
    Simulates the exact scenario that caused UniqueViolationError:
    per_asset_stage running multiple times within the same hour for GBPUSD.
    """
    session = test_db_session
    symbol = "GBPUSD"
    now_hour_str = "20260824_04"
    mon_key = f"context_drift_{symbol}_{now_hour_str}"
    
    # Run 1: First analysis in the hour
    payload_run1 = json.dumps({
        'cds_score': 0.3,
        'breakdown': {'spatial': 0.0, 'temporal': 1.0, 'task': 0.0, 'composite': 0.3},
        'timestamp': "2026-08-24T04:05:00+00:00"
    })
    await SystemConfig.upsert(session, key=mon_key, value=payload_run1)
    await session.commit()
    
    # Run 2: Second analysis in the same hour (e.g. trigger / retry at 04:24)
    payload_run2 = json.dumps({
        'cds_score': 0.35,
        'breakdown': {'spatial': 0.1, 'temporal': 1.0, 'task': 0.0, 'composite': 0.35},
        'timestamp': "2026-08-24T04:24:26+00:00"
    })
    await SystemConfig.upsert(session, key=mon_key, value=payload_run2)
    await session.commit()
    
    # Verify exactly 1 record exists with updated payload
    rows = (await session.execute(select(SystemConfig).where(SystemConfig.key == mon_key))).scalars().all()
    assert len(rows) == 1
    stored_data = json.loads(rows[0].value)
    assert stored_data['cds_score'] == 0.35
    assert stored_data['timestamp'] == "2026-08-24T04:24:26+00:00"

@pytest.mark.asyncio
async def test_debate_node_context_drift_query_updated_at(test_db_session):
    """
    Verifies that querying context drift ordering by SystemConfig.updated_at.desc()
    works properly without throwing AttributeError on non-existent 'id' column.
    """
    session = test_db_session
    sym = "GBPUSD"
    
    # Insert multiple keys
    await SystemConfig.upsert(session, key=f"context_drift_{sym}_20260824_03", value=json.dumps({
        'cds_score': 0.2, 'timestamp': '2026-08-24T03:00:00+00:00'
    }))
    await SystemConfig.upsert(session, key=f"context_drift_{sym}_20260824_04", value=json.dumps({
        'cds_score': 0.35, 'timestamp': '2026-08-24T04:00:00+00:00'
    }))
    await session.commit()
    
    # Query like debate_node.py
    mon_key = f'context_drift_{sym}'
    drift_cfg = (await session.execute(
        select(SystemConfig)
        .where(SystemConfig.key.like(f'{mon_key}%'))
        .order_by(SystemConfig.updated_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    
    assert drift_cfg is not None
    assert "context_drift_GBPUSD_" in drift_cfg.key
