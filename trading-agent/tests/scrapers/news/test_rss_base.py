import pytest
from unittest.mock import MagicMock, patch
from scrapers.news.rss_base import RssBaseScraper

class TestRssBaseScraper:
    def test_fetch_news_summary_only(self):
        
        mock_feedparser = MagicMock()
        mock_feed = MagicMock()
        mock_feed.entries = [
            {
                "link": "http://test.com/1",
                "title": "News 1",
                "published": "2023-01-01",
                "summary": "This is news 1"
            },
            {
                "link": "http://test.com/2",
                "title": "News 2",
                "pubDate": "2023-01-02",
                "description": [{"value": "<b>News 2 desc</b>"}] # should strip html
            },
            {
                # Missing link, should skip
                "title": "News 3"
            }
        ]
        mock_feedparser.parse.return_value = mock_feed
        
        scraper = RssBaseScraper("Test", "http://feed")
        
        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            news = scraper.fetch_news(limit=2)
        
        assert len(news) == 2
        assert news[0].title == "News 1"
        assert news[0].url == "http://test.com/1"
        assert news[0].summary == "This is news 1"
        
        assert news[1].title == "News 2"
        assert news[1].summary == "News 2 desc"
        assert news[1].timestamp == "2023-01-02"

    def test_fetch_news_updated_date_fallback(self):
        mock_feedparser = MagicMock()
        mock_feed = MagicMock()
        mock_feed.status = 200
        mock_feed.entries = [
            {
                "link": "http://test.com/dc",
                "title": "Dublin Core News",
                "updated": "2026-09-29T14:30:00+10:00",
                "description": "Rate hike decision"
            }
        ]
        mock_feedparser.parse.return_value = mock_feed
        scraper = RssBaseScraper("TestDC", "http://feed")

        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            news = scraper.fetch_news(limit=1)

        assert len(news) == 1
        assert news[0].title == "Dublin Core News"
        assert news[0].timestamp == "2026-09-29T04:30:00Z"

    def test_fetch_news_403_retry_fallback(self):
        mock_feedparser = MagicMock()
        first_feed = MagicMock()
        first_feed.status = 403
        first_feed.entries = []

        second_feed = MagicMock()
        second_feed.status = 200
        second_feed.entries = [
            {
                "link": "http://test.com/recovered",
                "title": "Recovered News",
                "pubDate": "2026-09-30",
                "summary": "Recovered after 403"
            }
        ]
        mock_feedparser.parse.side_effect = [first_feed, second_feed]
        scraper = RssBaseScraper("Test403", "http://feed")

        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            news = scraper.fetch_news(limit=1)

        assert len(news) == 1
        assert news[0].title == "Recovered News"
        assert mock_feedparser.parse.call_count == 2



