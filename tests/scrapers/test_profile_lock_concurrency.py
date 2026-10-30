import asyncio
from datetime import datetime, timezone
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.infrastructure.data_ingestion.scrapers.base_scraper import (
    BaseScraper,
    _PROFILE_LOCKS,
    _PROFILE_LOCKS_GUARD,
)


class TestProfileLockConcurrency:
    """
    Empirical tests validating ProfileLock behavior under multi-threaded
    supervisor-worker lifecycle, cross-thread timeout cleanup, and high-concurrency stress.
    """

    def setup_method(self):
        with _PROFILE_LOCKS_GUARD:
            _PROFILE_LOCKS.clear()

    def teardown_method(self):
        with _PROFILE_LOCKS_GUARD:
            _PROFILE_LOCKS.clear()

    @patch.object(BaseScraper, "_cleanup_stale_profile_locks")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_cross_thread_scraper_close_releases_profile_lock(self, mock_options, mock_page, mock_cleanup):
        """
        A/B verification test:
        Worker thread A instantiates BaseScraper with profile_name="test_cross_thread".
        Supervisor thread B simulates a timeout cleanup by calling scraper.close().
        Caller thread C must then be able to acquire the same profile without deadlocking!
        """
        scraper_container = []
        worker_ready = threading.Event()
        worker_can_exit = threading.Event()

        def worker_target():
            s = BaseScraper(headless=True, profile_name="test_cross_thread")
            scraper_container.append(s)
            worker_ready.set()
            worker_can_exit.wait(timeout=5.0)
            s.close()

        worker_thread = threading.Thread(target=worker_target, name="WorkerThread-A")
        worker_thread.start()
        assert worker_ready.wait(timeout=3.0), "Worker thread failed to initialize scraper in time"

        scraper = scraper_container[0]
        assert scraper._acquired_profile_lock is True

        # Supervisor thread B runs cleanup on timeout
        cleanup_success = []

        def supervisor_target():
            try:
                scraper.close()
                cleanup_success.append(True)
            except Exception as e:
                cleanup_success.append(e)

        supervisor_thread = threading.Thread(target=supervisor_target, name="SupervisorThread-B")
        supervisor_thread.start()
        supervisor_thread.join(timeout=3.0)

        assert cleanup_success == [True], f"Supervisor cleanup failed: {cleanup_success}"

        # Release worker thread so it can execute its finally block
        worker_can_exit.set()
        worker_thread.join(timeout=3.0)

        # Thread C now attempts to acquire the profile lock. It MUST succeed and not block!
        acquired_by_c = []

        def caller_c_target():
            s2 = BaseScraper(headless=True, profile_name="test_cross_thread")
            acquired_by_c.append(s2._acquired_profile_lock)
            s2.close()

        caller_thread = threading.Thread(target=caller_c_target, name="CallerThread-C")
        caller_thread.start()
        caller_thread.join(timeout=3.0)

        assert not caller_thread.is_alive(), "Caller thread C deadlocked waiting for orphaned lock!"
        assert acquired_by_c == [True], "Caller thread C failed to acquire profile lock"

    @patch.object(BaseScraper, "_cleanup_stale_profile_locks")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_concurrent_close_calls_are_thread_safe_and_idempotent(self, mock_options, mock_page, mock_cleanup):
        """
        Verify that calling close() concurrently from 5 threads on the same scraper
        does not crash, raise unhandled exceptions, or corrupt lock state.
        """
        scraper = BaseScraper(headless=True, profile_name="concurrent_close_test")
        exceptions = []

        def close_worker():
            try:
                scraper.close()
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=close_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert not exceptions, f"Exceptions occurred during concurrent close(): {exceptions}"
        assert scraper.is_closed is True
        assert scraper._acquired_profile_lock is False

    @patch.object(BaseScraper, "_cleanup_stale_profile_locks")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_profile_lock_timeout_fallback_to_ephemeral_profile(self, mock_options, mock_page, mock_cleanup):
        """
        If a profile lock is genuinely held by another active scraper on a different thread
        and cannot be acquired within the timeout, BaseScraper must gracefully fallback to
        an ephemeral temporary profile instead of blocking indefinitely and crashing the daemon.
        """
        scraper1_holder = []
        scraper1_ready = threading.Event()
        scraper1_can_exit = threading.Event()

        def holder_thread():
            s1 = BaseScraper(headless=True, profile_name="contested_profile")
            scraper1_holder.append(s1)
            scraper1_ready.set()
            scraper1_can_exit.wait(timeout=5.0)
            s1.close()

        t_holder = threading.Thread(target=holder_thread)
        t_holder.start()
        assert scraper1_ready.wait(timeout=3.0)

        try:
            scraper2_holder = []

            def contested_requester():
                with patch(
                    "monika.infrastructure.data_ingestion.scrapers.base_scraper.PROFILE_LOCK_TIMEOUT_SECONDS",
                    0.2,
                ):
                    s2 = BaseScraper(headless=True, profile_name="contested_profile")
                    scraper2_holder.append(s2)
                    s2.close()

            t_req = threading.Thread(target=contested_requester)
            t_req.start()
            t_req.join(timeout=3.0)

            assert not t_req.is_alive(), "Contested requester thread deadlocked!"
            assert len(scraper2_holder) == 1
            s2 = scraper2_holder[0]
            assert s2._temp_profile_dir is not None
            assert s2._acquired_profile_lock is False
        finally:
            scraper1_can_exit.set()
            t_holder.join(timeout=3.0)

    @patch.object(BaseScraper, "_cleanup_stale_profile_locks")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_high_concurrency_stress_no_deadlock(self, mock_options, mock_page, mock_cleanup):
        """
        High-concurrency stress test:
        12 worker threads simultaneously open, close, and cross-thread cancel
        scrapers on the same shared profile name with short timeouts.
        All threads MUST complete safely without deadlocks or unhandled exceptions.
        """
        errors = []
        scrapers = []
        num_workers = 12

        def worker_task(worker_id: int):
            try:
                for _ in range(3):
                    with patch(
                        "monika.infrastructure.data_ingestion.scrapers.base_scraper.PROFILE_LOCK_TIMEOUT_SECONDS",
                        0.1,
                    ):
                        s = BaseScraper(headless=True, profile_name="stress_shared_profile")
                        scrapers.append(s)
                        time.sleep(0.01)
                        s.close()
            except Exception as e:
                errors.append((worker_id, e))

        threads = [
            threading.Thread(target=worker_task, args=(i,), name=f"StressWorker-{i}") for i in range(num_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
            assert not t.is_alive(), f"Stress worker thread {t.name} deadlocked!"

        assert not errors, f"Errors encountered during stress test: {errors}"
        with _PROFILE_LOCKS_GUARD:
            lock = _PROFILE_LOCKS.get("stress_shared_profile")
            if lock:
                assert not lock.is_locked, "Lock remained locked after all workers finished!"

    @pytest.mark.asyncio
    async def test_active_calendar_poller_tier1_bypasses_browser_completely(self):
        """
        Verify that when Tier 1 ForexFactory direct feed resolves target events,
        InvestingCalendarScraper is NEVER initialized (zero browser overhead, zero lock contention).
        """
        from monika.application.scheduler.active_calendar_poller import ActiveCalendarPoller

        poller = ActiveCalendarPoller(settings={})
        poller.running = True
        poller.poll_interval = 0.01

        mock_event = MagicMock(id=101, event_name="Non-Farm Payrolls", currency="USD", impact="high")
        mock_event.actual = None

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.all.return_value = [mock_event]
        mock_exec_res.scalar_one_or_none.return_value = mock_event
        mock_session.execute.return_value = mock_exec_res

        mock_feed_item = MagicMock(event_name="Non-Farm Payrolls", actual="250K", forecast="200K", previous="180K")

        with (
            patch("monika.application.scheduler.active_calendar_poller.get_session") as mock_get_sess,
            patch(
                "monika.infrastructure.data_ingestion.scrapers.calendar.calendar_forexfactory.fetch_forexfactory_feed_direct",
                return_value=[mock_feed_item],
            ),
            patch("monika.application.scheduler.active_calendar_poller.InvestingCalendarScraper") as mock_inv_scraper,
        ):
            mock_get_sess.return_value.__aenter__.return_value = mock_session

            # Run polling task for event scheduled now
            now_utc = datetime.now(timezone.utc)
            await poller._poll_for_events(now_utc)

            # Assert Tier 1 resolved the data
            assert mock_event.actual == "250K"
            # Crucial architectural assertion: Browser scraper was NEVER instantiated!
            mock_inv_scraper.assert_not_called()
