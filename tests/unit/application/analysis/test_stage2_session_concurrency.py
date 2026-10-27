import asyncio
import threading
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.application.analysis.stages.per_asset.context_builder import ContextBuilderMixin
from monika.application.scheduler.unified_cron_engine import UnifiedCronEngine, UnifiedCronJob


@pytest.mark.asyncio
async def test_stage2_bundler_independent_sessions_concurrency():
    """Verify that multiple concurrent Stage2DataBundler instances maintain session isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    shared_macro_cache = {}

    async def run_fetch(sym: str):
        async with session_factory() as session:
            bundler = Stage2DataBundler(session, settings={}, shared_global_cache=shared_macro_cache)
            assert bundler.executor.session is session
            # Execute dummy query
            res = (await session.execute(text(f"SELECT '{sym}'"))).scalar()
            await asyncio.sleep(0.01)
            assert bundler.executor.session is session
            return res

    tasks = [run_fetch(f"SYM_{i}") for i in range(8)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, res in enumerate(results):
        assert not isinstance(res, Exception), f"Task {i} failed: {res}"
        assert res == f"SYM_{i}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_context_builder_fetch_stage2_bundle_no_session_leak():
    """Verify ContextBuilderMixin._fetch_stage2_bundle creates independent bundler instances."""

    class DummyRunner(ContextBuilderMixin):
        def __init__(self):
            self.settings = {}

    runner = DummyRunner()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def fetch_for_symbol(sym: str):
        async with session_factory() as session:
            with patch(
                "monika.application.analysis.prefetch.stage2_prefetcher.Stage2DataBundler.fetch_bundle",
                new_callable=AsyncMock,
            ) as mock_fetch:
                mock_fetch.return_value = ("bundle_content" * 50, {"symbol": sym})
                bundle, raw_data, success, guidance = await runner._fetch_stage2_bundle(session, sym, cot_code="")
                assert success is True
                assert raw_data["symbol"] == sym
                return sym

    tasks = [fetch_for_symbol(f"SYM_{i}") for i in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        assert not isinstance(res, Exception)

    # Ensure self._stage2_bundler is NOT cached on runner
    assert not hasattr(runner, "_stage2_bundler")
    assert hasattr(runner, "_shared_macro_cache")

    await engine.dispose()


@pytest.mark.asyncio
async def test_unified_cron_engine_main_loop_dispatch(tmp_path):
    """Verify that UnifiedCronEngine dispatches coroutine jobs to the provided main loop."""
    current_loop = asyncio.get_running_loop()
    db_file = str(tmp_path / "cron_test.db")
    engine = UnifiedCronEngine(db_path=db_file, loop=current_loop)

    executed_on_loop = None

    def my_callback(job: UnifiedCronJob):
        async def _coro():
            nonlocal executed_on_loop
            executed_on_loop = asyncio.get_running_loop()
            return "SUCCESS"

        return _coro()

    engine.register_execution_callback(my_callback)

    test_job = UnifiedCronJob(
        job_id="test_main_loop_job",
        schedule_expression="every 1m",
        prompt="run check",
        target_delivery="session",
    )

    # Register job so pending_slot update succeeds
    engine.register_job(
        job_id=test_job.job_id,
        schedule_expression=test_job.schedule_expression,
        prompt=test_job.prompt,
        target_delivery=test_job.target_delivery,
    )

    # Dispatch from background thread while main loop is awaiting
    def thread_dispatch():
        engine._dispatch_job(test_job)

    await asyncio.to_thread(thread_dispatch)

    assert executed_on_loop is current_loop
    engine.close()
