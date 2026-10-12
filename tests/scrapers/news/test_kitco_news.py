import pytest
from unittest.mock import MagicMock, patch
from scrapers.news.kitco_news import KitcoNewsScraper

class TestKitcoNewsScraper:
    @patch("scrapers.news.kitco_news.BaseScraper._initialize_browser")
    def test_fetch_news_fail(self, mock_init):
        scraper = KitcoNewsScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=False)
        news = scraper.fetch_news()
        assert news == []

    @patch("scrapers.news.kitco_news.BaseScraper._initialize_browser")
    def test_fetch_news_success(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = KitcoNewsScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=True)
        
        # Mock articles
        a1 = MagicMock()
        a1.attr.return_value = "/news/article/123"
        a1.text = "Title 1\nSummary 1\nTime 1"
        
        a2 = MagicMock()
        a2.attr.return_value = "https://www.kitco.com/news/article/456"
        a2.text = "Short" # should be skipped because len <= 20
        
        a3 = MagicMock()
        a3.attr.return_value = None # skipped
        
        mock_page.eles.return_value = [a1, a2, a3]
        
        news = scraper.fetch_news(limit=5)
        
        assert len(news) == 1
        assert news[0].title == "Title 1"
        assert news[0].summary == "Summary 1"
        assert news[0].timestamp is not None
        assert len(news[0].timestamp) >= 10
        assert news[0].url == "https://www.kitco.com/news/article/123"
