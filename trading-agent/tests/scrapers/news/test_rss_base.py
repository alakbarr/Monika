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


