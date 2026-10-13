# ==============================================================================
# File: tests/test_database_concurrency.py
# ==============================================================================

import asyncio
from pathlib import Path
import pytest
from sqlalchemy import select, func

import database.db as db_mod
from database.db import get_session, get_write_session, init_db, close_db
from database.models import Base, Trade, ActivityLog
from logging_observability.activity_logger import ActivityLogger


@pytest.fixture
async def setup_sqlite_concurrency_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Setup an isolated temporary file-based SQLite database configured with WAL mode
    and connection pooling to stress-test concurrent reader and writer operations.
    """
    db_file = tmp_path / "concurrency_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    # Close existing engine if open
    await close_db()

    # Configure environment for temporary test database
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("MONIKA_TIER", "trial")

    # Unpatch get_sessionmaker in database.db if mocked by conftest
    orig_sessionmaker_factory = db_mod.get_sessionmaker
    if hasattr(db_mod, "_orig_get_sessionmaker"):
        orig_sessionmaker_factory = getattr(db_mod, "_orig_get_sessionmaker")
    monkeypatch.setattr(db_mod, "get_sessionmaker", orig_sessionmaker_factory)

    # Reset module engine state
    db_mod.engine = None
    db_mod._async_session_factory = None
    db_mod._SQLITE_WRITE_LOCKS.clear()

    # Initialize schema
    await init_db()

    yield db_file

    # Teardown and clean locks
    await close_db()


class TestDatabaseConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_readers(self, setup_sqlite_concurrency_db: Path):
        """Verify 20 concurrent readers execute without lock contention or pool exhaustion."""
        # Seed initial data
        async with get_write_session() as session:
            for i in range(5):
                session.add(
                    Trade(
                        symbol=f"SEED{i}",
                        direction="BUY",
                        entry_price=100.0 + i,
                        volume=0.1,
                        status="OPEN",
                    )
                )

        async def reader_task(reader_id: int) -> int:
            async with get_session() as session:
                res = await session.execute(select(Trade))
                trades = res.scalars().all()
                return len(trades)

        tasks = [reader_task(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 20
        assert all(count == 5 for count in results)

    @pytest.mark.asyncio
    async def test_concurrent_writers(self, setup_sqlite_concurrency_db: Path):
        """Verify 10 concurrent writers serialize safely through get_write_session."""

        async def writer_task(writer_id: int) -> None:
            async with get_write_session() as session:
                session.add(
                    Trade(
                        symbol=f"WRITER_{writer_id}",
                        direction="BUY" if writer_id % 2 == 0 else "SELL",
                        entry_price=200.0 + writer_id,
                        volume=1.0,
                        status="OPEN",
                    )
                )

        tasks = [writer_task(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all 10 records are committed safely
        async with get_session() as session:
            res = await session.execute(select(func.count(Trade.id)))
            count = res.scalar()
            assert count == 10

    @pytest.mark.asyncio
    async def test_mixed_concurrent_readers_and_writers(self, setup_sqlite_concurrency_db: Path):
        """Verify mixed workload: 20 readers and 10 writers running concurrently in WAL mode."""
        read_successes = []

        async def reader_task(reader_id: int) -> None:
            for _ in range(3):
                async with get_session() as session:
                    res = await session.execute(select(func.count(Trade.id)))
                    _ = res.scalar()
                    await asyncio.sleep(0.005)
            read_successes.append(reader_id)

        async def writer_task(writer_id: int) -> None:
            async with get_write_session() as session:
                session.add(
                    Trade(
                        symbol=f"MIXED_{writer_id}",
                        direction="BUY",
                        entry_price=300.0 + writer_id,
                        volume=0.5,
                        status="OPEN",
                    )
                )
                await asyncio.sleep(0.01)

        readers = [reader_task(i) for i in range(20)]
        writers = [writer_task(i) for i in range(10)]

        await asyncio.gather(*(readers + writers))

        assert len(read_successes) == 20

        async with get_session() as session:
            res = await session.execute(select(func.count(Trade.id)))
            count = res.scalar()
            assert count == 10

    @pytest.mark.asyncio
    async def test_rollback_safety_under_concurrency(self, setup_sqlite_concurrency_db: Path):
        """Verify failure in write transaction triggers safe rollback without wedging mutex."""

        async def failing_writer(writer_id: int) -> None:
            try:
                async with get_write_session() as session:
                    session.add(
                        Trade(
                            symbol=f"FAIL_{writer_id}",
                            direction="BUY",
                            entry_price=400.0,
                            volume=1.0,
                            status="OPEN",
                        )
                    )
                    raise RuntimeError(f"Simulated crash in writer {writer_id}")
            except RuntimeError:
                pass

        async def succeeding_writer(writer_id: int) -> None:
            async with get_write_session() as session:
                session.add(
                    Trade(
                        symbol=f"OK_{writer_id}",
                        direction="BUY",
                        entry_price=500.0,
                        volume=1.0,
                        status="OPEN",
                    )
                )

        interleaved = []
        for i in range(6):
            if i % 2 == 0:
                interleaved.append(failing_writer(i))
            else:
                interleaved.append(succeeding_writer(i))

        await asyncio.gather(*interleaved)

        # Exactly 3 successful writes should be recorded, failing writes must be rolled back
        async with get_session() as session:
            res = await session.execute(select(Trade))
            trades = res.scalars().all()
            assert len(trades) == 3
            assert all(t.symbol.startswith("OK_") for t in trades)

    @pytest.mark.asyncio
    async def test_activity_logger_concurrency(self, setup_sqlite_concurrency_db: Path):
        """Verify ActivityLogger handles concurrent single and bulk logging without session leaks or locking errors."""
        logger_instance = ActivityLogger()

        async def log_task(task_id: int) -> None:
            await logger_instance.log(
                category="system",
                description=f"Concurrency log event from task {task_id}",
                related_id=task_id,
                actor=f"worker_{task_id}",
            )

        async def bulk_task(task_id: int) -> None:
            entries = [
                {
                    "category": "trading",
                    "description": f"Bulk trade entry {j} from worker {task_id}",
                    "related_id": task_id * 10 + j,
                    "actor": f"bulk_worker_{task_id}",
                }
                for j in range(3)
            ]
            await logger_instance.bulk(entries)

        single_tasks = [log_task(i) for i in range(15)]
        bulk_tasks = [bulk_task(i) for i in range(5)]
        await asyncio.gather(*(single_tasks + bulk_tasks))

        # 15 single system logs + (5 * 3 = 15) bulk trading logs = 30 logs total
        async with get_session() as session:
            res_single = await session.execute(
                select(func.count(ActivityLog.id)).where(ActivityLog.category == "system")
            )
            count_single = res_single.scalar()
            assert count_single == 15

            res_bulk = await session.execute(
                select(func.count(ActivityLog.id)).where(ActivityLog.category == "trading")
            )
            count_bulk = res_bulk.scalar()
            assert count_bulk == 15
