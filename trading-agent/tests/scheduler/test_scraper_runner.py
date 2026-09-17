import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from scheduler.scraper_runner import ScraperRunner

class TestScraperRunner:
    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "schedule": {
                    "scraper_stagger_seconds": 0
                }
            },
            "scraping": {
                "consecutive_failure_alert": 3,
                "sources": {
                    "rss_bloomberg": {"enabled": True},
                    "investing_calendar": {"enabled": True},
                    "tradingview": {"enabled": True},
                    "kitco": {"enabled": True},
                    "cme_fedwatch": {"enabled": True},
                    "twitter": {"enabled": True}
                }
            }
        }

    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.ScraperRunner._run_rss_scrapers")
    @patch("scheduler.scraper_runner.ScraperRunner._run_single")
    async def test_run_all_enabled(self, mock_single, mock_rss, settings):
        # _run_single used for all non-RSS scrapers
        mock_rss.return_value = {"saved": 10}
        mock_single.return_value = {"saved": 5}

        runner = ScraperRunner(settings)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await runner.run_all()

        assert res["rss"]["saved"] == 10
        assert "calendar" in res
        assert "tradingview" in res
        assert "kitco" in res
        assert "fedwatch" in res
        assert "twitter" in res
        mock_rss.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.ScraperRunner._run_rss_scrapers")
    @patch("scheduler.scraper_runner.ScraperRunner._run_single")
    async def test_run_all_disabled(self, mock_single, mock_rss, settings):
        settings["scraping"]["sources"]["investing_calendar"]["enabled"] = False
        settings["scraping"]["sources"]["tradingview"]["enabled"] = False
        settings["scraping"]["sources"]["kitco"]["enabled"] = False
        settings["scraping"]["sources"]["cme_fedwatch"]["enabled"] = False
        settings["scraping"]["sources"]["twitter"]["enabled"] = False

        mock_rss.return_value = {"saved": 5}

        runner = ScraperRunner(settings)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await runner.run_all()

        assert "rss" in res
        assert "calendar" not in res
        assert "tradingview" not in res
        mock_rss.assert_awaited_once()
        mock_single.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.get_session")
    @patch("scheduler.scraper_runner.batch_save_news")
    async def test_run_rss_scrapers(self, mock_save_news, mock_get_session, settings):
        # Only bloomberg=True — all others disabled explicitly
        settings["scraping"]["sources"] = {
            # Phase 4.3 central bank feeds — disabled for this test
            "rss_fed": {"enabled": False},
            "rss_ecb": {"enabled": False},
            "rss_boe": {"enabled": False},
            # Third-party feeds
            "rss_bloomberg": {"enabled": True},
            "rss_wsj": {"enabled": False},
            "rss_marketwatch": {"enabled": False},
            "rss_dow_jones": {"enabled": False},
            "rss_forexlive": {"enabled": False},
            "rss_fxstreet": {"enabled": False},
            "rss_investing": {"enabled": False},
            "rss_coindesk": {"enabled": False},
            "rss_boj": {"enabled": False},
            "rss_rba": {"enabled": False},
            "rss_reuters": {"enabled": False},
            "rss_cnbc": {"enabled": False},
            "rss_ft": {"enabled": False},
        }

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        mock_save_news.return_value = 5

        runner = ScraperRunner(settings)
        runner._run_in_executor = AsyncMock(return_value=[{"title": "test"}])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await runner._run_rss_scrapers()

        # Only bloomberg enabled → 1 scraper × 5 saved
        assert res["saved"] == 5


    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.get_session")
    @patch("scheduler.scraper_runner.batch_save_calendar")
    async def test_run_calendar(self, mock_save_cal, mock_get_session, settings):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        mock_save_cal.return_value = 10

        runner = ScraperRunner(settings)
        runner._run_in_executor = AsyncMock(return_value=[])

        res = await runner._fetch_calendar()
        assert res["saved"] == 10

    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.get_session")
    @patch("scheduler.scraper_runner.batch_save_fedwatch")
    async def test_run_fedwatch_error(self, mock_save_fedwatch, mock_get_session, settings):
        runner = ScraperRunner(settings)
        runner._run_in_executor = AsyncMock(side_effect=Exception("Failed to scrape"))

        res = await runner._run_single("fedwatch", runner._fetch_fedwatch)
        assert "error" in res
        assert "Failed to scrape" in res["error"]

    @pytest.mark.asyncio
    async def test_consecutive_failure_alert(self, settings):
        """Alert fires after threshold consecutive failures."""
        runner = ScraperRunner(settings)

        async def _bad_fetch():
            raise Exception("scraper down")

        notified = []

        async def mock_warn(msg):
            notified.append(msg)

        with patch("utils.infra.notifier.AgentNotifier") as mock_notifier_cls:
            mock_notifier = mock_notifier_cls.return_value
            mock_notifier.send_warning = AsyncMock(side_effect=mock_warn)

            for i in range(3):
                res = await runner._run_single("test_scraper", _bad_fetch)
                assert "error" in res

        # After 3 consecutive failures, alert should have fired
        assert runner._consecutive_failures.get("test_scraper") == 3

    def test_stop_closes_active_scrapers(self, settings):
        """ScraperRunner.stop() must forcibly close all registered active scrapers."""
        runner = ScraperRunner(settings)
        mock_scraper_1 = MagicMock()
        mock_scraper_2 = MagicMock()
        
        runner._register_scraper(mock_scraper_1)
        runner._register_scraper(mock_scraper_2)
        assert len(runner._active_scrapers) == 2
        
        runner.stop()
        assert not runner._running
        assert len(runner._active_scrapers) == 0
        mock_scraper_1.close.assert_called_once()
        mock_scraper_2.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.get_session")
    @patch("scheduler.scraper_runner.batch_save_calendar")
    async def test_fetch_calendar_investing_success(self, mock_save_cal, mock_get_session, settings):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        mock_save_cal.return_value = 15

        runner = ScraperRunner(settings)
        runner._run_in_executor = AsyncMock(return_value=[MagicMock()])

        res = await runner._fetch_calendar()
        assert res["saved"] == 15
        assert res["source"] == "investing"

    @pytest.mark.asyncio
    @patch("scheduler.scraper_runner.get_session")
    @patch("scheduler.scraper_runner.batch_save_calendar")
    async def test_fetch_calendar_fallback_to_forexfactory(self, mock_save_cal, mock_get_session, settings):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        mock_save_cal.return_value = 8

        runner = ScraperRunner(settings)
        # First call (Investing) raises Exception, Second call (ForexFactory) succeeds
        runner._run_in_executor = AsyncMock(side_effect=[Exception("Investing timeout"), [MagicMock()]])

        res = await runner._fetch_calendar()
        assert res["saved"] == 8
        assert res["source"] == "forexfactory"

    @pytest.mark.asyncio
    async def test_scraper_custom_timeouts(self, settings):
        runner = ScraperRunner(settings)
        from scheduler.scraper_runner import DEFAULT_SCRAPER_TIMEOUTS
        assert DEFAULT_SCRAPER_TIMEOUTS["calendar"] == 180.0
        assert DEFAULT_SCRAPER_TIMEOUTS["fedwatch"] == 120.0
        assert DEFAULT_SCRAPER_TIMEOUTS["rss"] == 60.0

    @pytest.mark.asyncio
    async def test_run_all_aborts_when_stopped(self, settings):
        """run_all() should immediately abort if stopped."""
        runner = ScraperRunner(settings)
        runner._running = False
        res = await runner.run_all()
        assert res == {}

    @patch("scrapers.base_scraper.kill_process_tree")
    def test_cleanup_timed_out_scrapers_kills_process_trees(self, mock_kill, settings):
        runner = ScraperRunner(settings)
        scraper1 = MagicMock()
        scraper1.browser_pid = 5555
        scraper2 = MagicMock()
        scraper2.browser_pid = None

        runner._register_scraper(scraper1)
        runner._register_scraper(scraper2)
        assert len(runner._active_scrapers) == 2

        cleaned = runner._cleanup_timed_out_scrapers()
        assert cleaned == 2
        assert len(runner._active_scrapers) == 0
        scraper1.close.assert_called_once()
        scraper2.close.assert_called_once()
        mock_kill.assert_called_once_with(5555)

    @pytest.mark.asyncio
    @patch("scrapers.base_scraper.kill_process_tree")
    async def test_run_single_timeout_triggers_cleanup(self, mock_kill, settings):
        runner = ScraperRunner(settings)
        scraper = MagicMock()
        scraper.browser_pid = 6666
        runner._register_scraper(scraper)

        fetch_mock = AsyncMock(side_effect=asyncio.TimeoutError())
        res = await runner._run_single("tradingview", fetch_mock)

        assert "error" in res
        assert "timed out" in res["error"]
        assert len(runner._active_scrapers) == 0
        scraper.close.assert_called_once()
        mock_kill.assert_called_once_with(6666)



