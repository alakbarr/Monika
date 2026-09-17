# ==============================================================================
# File: tests/test_scraper_check_scripts.py
# ==============================================================================

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from scrapers.models import CalendarEvent, ScrapedNews, FedMeeting, FedProbability, ScrapedTweet

# Import helper functions from check scripts
from scripts.check_scrapers.check_calendar import check_forexfactory, check_investing, check_finnhub, print_events_table
from scripts.check_scrapers.check_news import check_kitco, check_tradingview, check_single_rss, get_rss_map, print_news_table
from scripts.check_scrapers.check_cme import check_cme_fedwatch, print_fed_meetings
from scripts.check_scrapers.check_sentiment import check_fxssi, check_myfxbook, check_binance, print_ratios_table
from scripts.check_scrapers.check_twitter import check_twitter, print_tweets_table, check_twitter_sessions


class TestCheckCalendar:
    @patch("scrapers.calendar.calendar_forexfactory.ForexFactoryCalendarScraper")
    def test_check_forexfactory_success(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_events.return_value = [
            CalendarEvent(time="08:30", currency="USD", impact="High", event_name="CPI m/m")
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_forexfactory(headless=True, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1
        mock_instance.close.assert_called_once()

    @patch("scrapers.calendar.calendar_forexfactory.ForexFactoryCalendarScraper")
    def test_check_forexfactory_error(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_events.side_effect = RuntimeError("Network error")
        mock_scraper_cls.return_value = mock_instance

        res = check_forexfactory(headless=True, pause=0)
        assert res["status"] == "FAILED"
        assert "Network error" in res["error"]

    @patch("scrapers.calendar.calendar_investing.InvestingCalendarScraper")
    def test_check_investing_success(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_events.return_value = [
            CalendarEvent(time="14:00", currency="USD", impact="High", event_name="Fed Interest Rate Decision")
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_investing(headless=True, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1
        mock_instance.close.assert_called_once()

    @patch("scrapers.calendar.calendar_finnhub.FinnhubCalendarScraper")
    def test_check_finnhub_success(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.api_key = "mock_key"
        mock_instance.fetch_today_events.return_value = [
            CalendarEvent(time="10:00", currency="USD", impact="Medium", event_name="Retail Sales")
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_finnhub()
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1

    def test_print_events_table(self, capsys):
        events = [CalendarEvent(time="10:00", currency="USD", impact="High", event_name="CPI")]
        print_events_table(events)
        captured = capsys.readouterr()
        assert "CPI" in captured.out
        assert "USD" in captured.out


class TestCheckNews:
    @patch("scrapers.news.kitco_news.KitcoNewsScraper")
    def test_check_kitco_success(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_news.return_value = [
            ScrapedNews(title="Gold prices surge", url="https://kitco.com/1", source="Kitco", timestamp="2026-08-23")
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_kitco(headless=True, limit=5, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1
        mock_instance.close.assert_called_once()

    @patch("scrapers.news.tradingview_news.TradingViewNewsScraper")
    def test_check_tradingview_success(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_news.return_value = [
            ScrapedNews(title="Oil prices climb", url="https://tradingview.com/1", source="TradingView", timestamp="2026-08-23")
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_tradingview(headless=True, limit=5, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1
        mock_instance.close.assert_called_once()

    def test_get_rss_map(self):
        rss_map = get_rss_map()
        assert "fed" in rss_map
        assert "bloomberg" in rss_map
        assert "reuters" in rss_map
        assert len(rss_map) >= 16

    def test_check_single_rss(self):
        mock_cls = MagicMock()
        mock_inst = MagicMock()
        mock_inst.fetch_news.return_value = [
            ScrapedNews(title="Fed announcement", url="https://fed.gov/1", source="Fed", timestamp="2026-08-23")
        ]
        mock_cls.return_value = mock_inst

        res = check_single_rss("fed", "Fed Official", mock_cls, limit=2)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1

    def test_print_news_table(self, capsys):
        news = [ScrapedNews(title="Market rally", url="https://test.com", source="Test", timestamp="2026-08-23")]
        print_news_table(news)
        captured = capsys.readouterr()
        assert "Market rally" in captured.out


class TestCheckCME:
    @patch("scrapers.macro.cme_fedwatch.FedWatchScraper")
    def test_check_cme_fedwatch_success(self, mock_scraper_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_probabilities.return_value = [
            FedMeeting(
                meeting_date="2026-09-16",
                current_rate_ref=5.25,
                probabilities=[FedProbability(target_range="500-525", probability=85.0, action="HOLD")],
                most_likely="HOLD"
            )
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_cme_fedwatch(headless=True, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1
        mock_instance.close.assert_called_once()

    def test_print_fed_meetings(self, capsys):
        meetings = [
            FedMeeting(
                meeting_date="2026-09-16",
                current_rate_ref=5.25,
                probabilities=[FedProbability(target_range="500-525", probability=85.0, action="HOLD")],
                most_likely="HOLD"
            )
        ]
        print_fed_meetings(meetings)
        captured = capsys.readouterr()
        assert "2026-09-16" in captured.out
        assert "HOLD" in captured.out


class TestCheckSentiment:
    @patch("scrapers.sentiment.fxssi_sentiment.FXSSISentimentFetcher")
    def test_check_fxssi_success(self, mock_fetcher_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_sync.return_value = {
            "source": "fxssi",
            "ratios": {"EURUSD": {"long_percent": 45.0, "short_percent": 55.0, "long_short_ratio": 0.82}}
        }
        mock_fetcher_cls.return_value = mock_instance

        res = check_fxssi(headless=True, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1

    @patch("scrapers.sentiment.myfxbook_sentiment.MyFxBookSentimentFetcher")
    def test_check_myfxbook_success(self, mock_fetcher_cls):
        mock_instance = MagicMock()
        mock_instance.fetch_sync.return_value = {
            "source": "myfxbook",
            "ratios": {"XAUUSD": {"long_percent": 60.0, "short_percent": 40.0, "long_short_ratio": 1.5}}
        }
        mock_fetcher_cls.return_value = mock_instance

        res = check_myfxbook(headless=True, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1

    @pytest.mark.asyncio
    @patch("scrapers.sentiment.binance_sentiment.BinanceSentimentFetcher")
    async def test_check_binance_success(self, mock_fetcher_cls):
        mock_instance = MagicMock()
        mock_instance.fetch = AsyncMock(return_value={
            "source": "binance_futures",
            "ratios": {"BTCUSDT": {"long_percent": 52.0, "short_percent": 48.0, "long_short_ratio": 1.08}}
        })
        mock_fetcher_cls.return_value = mock_instance

        res = await check_binance()
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1

    def test_print_ratios_table(self, capsys):
        ratios = {"EURUSD": {"long_percent": 45.0, "short_percent": 55.0, "long_short_ratio": 0.82}}
        print_ratios_table("FXSSI", ratios)
        captured = capsys.readouterr()
        assert "EURUSD" in captured.out
        assert "45.0%" in captured.out


class TestCheckTwitter:
    @patch("scrapers.social.twitter_watch.TwitterWatchScraper")
    def test_check_twitter_success(self, mock_scraper_cls, tmp_path):
        mock_instance = MagicMock()
        mock_instance.session_dir = tmp_path
        mock_instance.fetch_latest_tweets.return_value = [
            ScrapedTweet(id="123", username="federalreserve", content="FOMC Statement released", url="https://x.com/123", timestamp="2026-08-23T05:00:00Z")
        ]
        mock_scraper_cls.return_value = mock_instance

        res = check_twitter(headless=True, pause=0)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 1
        mock_instance.close.assert_called_once()

    def test_print_tweets_table(self, capsys):
        tweets = [
            ScrapedTweet(id="123", username="testuser", content="Breaking economic news", url="https://x.com/123", timestamp="2026-08-23")
        ]
        print_tweets_table(tweets)
        captured = capsys.readouterr()
        assert "@testuser" in captured.out
        assert "Breaking economic news" in captured.out
