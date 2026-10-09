"""
Test suite verifying SQLite concurrency resilience, BEGIN IMMEDIATE isolation,
and prevention of cascading PendingRollbackErrors across background tasks.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from database.models import Base, SystemConfig, PriceOHLCV
from database.safe_ops import safe_commit, safe_db_op


@pytest.mark.asyncio
async def test_sqlite_begin_immediate_concurrency(tmp_path):
    """
    Verify that SQLite engine configured with BEGIN IMMEDIATE allows concurrent
    read-then-write transactions without throwing database is locked deadlocks.
    """
    from sqlalchemy import event

    db_path = tmp_path / "test_concurrency.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url, connect_args={"timeout": 60.0})

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            dbapi_connection.isolation_level = None
        except Exception:
            pass
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _do_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def task_worker(worker_id: str, hold_sec: float):
        async with sm() as session:
            # 1. Read first (in deferred mode this would take a SHARED lock and deadlock)
            _ = (await session.execute(select(SystemConfig))).scalars().all()
            await asyncio.sleep(hold_sec)
            # 2. Write
            session.add(SystemConfig(key=f"worker_{worker_id}", value=f"val_{worker_id}"))
            # 3. Commit
            ok = await safe_commit(session, label=f"worker_{worker_id}")
            assert ok is True

    # Run 4 workers concurrently with read-then-write pattern
    results = await asyncio.gather(
        task_worker("A", 0.04),
        task_worker("B", 0.02),
        task_worker("C", 0.01),
        task_worker("D", 0.03),
        return_exceptions=True,
    )

    for r in results:
        assert not isinstance(r, Exception), f"Worker failed with exception: {r}"

    # Verify all 4 rows were saved cleanly
    async with sm() as session:
        rows = (await session.execute(select(SystemConfig))).scalars().all()
        assert len(rows) == 4

    await engine.dispose()


@pytest.mark.asyncio
async def test_safe_commit_cleans_session_on_failure():
    """Verify that safe_commit calls rollback and expunge_all when commit fails."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.commit.side_effect = Exception("Simulated commit error")
    mock_session.rollback = AsyncMock()
    mock_session.expunge_all = MagicMock()
    mock_session.is_active = False

    success = await safe_commit(mock_session, label="test_fail")
    assert success is False
    assert mock_session.rollback.called
    assert mock_session.expunge_all.called


@pytest.mark.asyncio
async def test_safe_db_op_cleans_session_on_failure():
    """Verify that safe_db_op calls rollback and expunge_all on failure."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.rollback = AsyncMock()
    mock_session.expunge_all = MagicMock()

    async def broken_op(session):
        raise RuntimeError("Operation error")

    res = await safe_db_op(mock_session, broken_op, default="fallback")
    assert res == "fallback"
    assert mock_session.rollback.called
    assert mock_session.expunge_all.called


@pytest.mark.asyncio
async def test_fetch_and_save_all_resilient_to_pair_failure():
    """
    Verify that if saving one pair fails in MT5Client.fetch_and_save_all,
    the session is cleanly rolled back and remaining pairs succeed.
    """
    from execution.mt5_client import MT5Client
    import pandas as pd

    client = MT5Client({})
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.rollback = AsyncMock()
    mock_session.expunge_all = MagicMock()

    sample_df = pd.DataFrame([
        {"time": 1700000000, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100}
    ])

    call_count = 0
    async def mock_get_ohlcv(symbol, tf, count):
        return sample_df

    async def mock_save_ohlcv(session, symbol, tf, df):
        nonlocal call_count
        call_count += 1
        if symbol == "USDJPY":
            raise RuntimeError("Database lock simulation on USDJPY")
        return 1

    client.get_ohlcv = mock_get_ohlcv
    client.save_ohlcv = mock_save_ohlcv

    results = await client.fetch_and_save_all(
        mock_session,
        symbols=["USDJPY", "EURUSD", "GBPUSD"],
        timeframes=["H1"],
    )

    assert results["USDJPY/H1"] == 0
    assert results["EURUSD/H1"] == 1
    assert results["GBPUSD/H1"] == 1
    # Verify rollback and expunge_all were called on the failed USDJPY pair
    assert mock_session.rollback.called
    assert mock_session.expunge_all.called


@pytest.mark.asyncio
async def test_technical_indicators_resilient_to_pair_failure():
    """
    Verify that if computing one pair fails in TechnicalIndicatorCalculator,
    the session is cleaned and remaining pairs continue.
    """
    from indicators.technical import TechnicalIndicatorCalculator

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.rollback = AsyncMock()
    mock_session.expunge_all = MagicMock()

    calc = TechnicalIndicatorCalculator(mock_session, {})

    async def mock_compute_and_save(symbol, tf):
        if symbol == "USDJPY":
            raise RuntimeError("Lock error simulation on USDJPY")
        return 10

    calc.compute_and_save = mock_compute_and_save

    results = await calc.compute_all_symbols(
        symbols=["USDJPY", "EURUSD"],
        timeframes=["H1"],
    )

    assert results["USDJPY/H1"] == 0
    assert results["EURUSD/H1"] == 10
    assert mock_session.rollback.called
    assert mock_session.expunge_all.called
