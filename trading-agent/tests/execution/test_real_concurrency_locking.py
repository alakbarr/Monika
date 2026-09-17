"""
Integration tests for PostgreSQL Transactional Advisory Lock & Concurrency Contention.
Verifies fail-closed behavior and real concurrent access serialization.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from database.db import transactional_advisory_lock


@pytest.mark.asyncio
async def test_transactional_advisory_lock_fail_closed_on_postgres_error():
    """Verify that when PostgreSQL advisory lock raises a database exception, it yields False (Fail-Closed)."""
    mock_session = MagicMock()
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.get_bind.return_value = mock_bind
    mock_session.execute = AsyncMock(side_effect=RuntimeError("Database connection blip / socket timeout"))

    async with transactional_advisory_lock(mock_session) as acquired:
        assert acquired is False, "Transactional advisory lock must fail-closed (False) on DB error"


@pytest.mark.asyncio
async def test_real_concurrency_in_memory_lock_contention():
    """Verify that concurrent coroutines acquire the in-memory fallback lock sequentially."""
    active_coros = []
    max_concurrent = 0

    async def worker(worker_id: int):
        nonlocal max_concurrent
        mock_session = MagicMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "sqlite"
        mock_session.get_bind.return_value = mock_bind

        async with transactional_advisory_lock(mock_session) as acquired:
            assert acquired is True
            active_coros.append(worker_id)
            if len(active_coros) > max_concurrent:
                max_concurrent = len(active_coros)
            await asyncio.sleep(0.05)
            active_coros.remove(worker_id)

    # Run 5 workers concurrently
    await asyncio.gather(*(worker(i) for i in range(5)))

    # Only 1 worker should be inside the critical section at any single time
    assert max_concurrent == 1
