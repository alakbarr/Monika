import pytest
from unittest.mock import MagicMock, patch
from scrapers.news.tradingview_news import TradingViewNewsScraper

class TestTradingViewNewsScraper:
    @patch("scrapers.news.tradingview_news.BaseScraper._initialize_browser")
    def test_fetch_news_fail(self, mock_init):
        scraper = TradingViewNewsScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=False)
        news = scraper.fetch_news()
        assert news == []

    @patch("scrapers.news.tradingview_news.BaseScraper._initialize_browser")
    @patch("os.path.exists")
    def test_fetch_news_success(self, mock_exists, mock_init):
        mock_exists.return_value = False # don't test json loading here
        
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = TradingViewNewsScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=True)
        
        # Mock articles
        a1 = MagicMock()
        mock_parent = MagicMock()
        mock_parent.attr.return_value = "/news/article-123"
        a1.parent.return_value = mock_parent
        
        # Elements inside a1
        title_ele = MagicMock()
        title_ele.text = "This is a very long title for testing"
        time_ele = MagicMock()
        time_ele.attr.return_value = "1620000000"
        body_ele = MagicMock()
        body_ele.text = "This is a very long body summary for testing"
        
        a1.ele.side_effect = lambda sel, timeout=None: title_ele if "title" in sel else (time_ele if "time" in sel else body_ele)
    
        mock_page.eles.side_effect = lambda sel, timeout=None: [a1] if "news-headline-card" in sel else [body_ele]
        
        news = scraper.fetch_news(limit=5)
        
        assert len(news) == 1
        assert news[0].title == "This is a very long title for testing"
        assert news[0].summary == "This is a very long body summary for testing"
        assert news[0].timestamp == "1620000000"
        assert news[0].url == "https://www.tradingview.com/news/article-123"

    @patch("scrapers.news.tradingview_news.BaseScraper._initialize_browser")
    def test_fetch_news_aborts_when_closed(self, mock_init):
        scraper = TradingViewNewsScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=True)
        scraper.is_closed = True
        news = scraper.fetch_news(limit=5)
        assert news == []

    @patch("scrapers.news.tradingview_news.BaseScraper._initialize_browser")
    def test_configurable_watchlist_id(self, mock_init):
        # 1. Custom parameter
        s1 = TradingViewNewsScraper(watchlist_id="999999")
        assert s1.target_url == "https://www.tradingview.com/news-flow/?watchlist=999999"

        # 2. Via settings dict
        s2 = TradingViewNewsScraper(settings={"scraping": {"tradingview_watchlist_id": "888888"}})
        assert s2.target_url == "https://www.tradingview.com/news-flow/?watchlist=888888"

        # 3. Via environment variable
        import os
        with patch.dict(os.environ, {"TRADINGVIEW_WATCHLIST_ID": "777777"}):
            s3 = TradingViewNewsScraper()
            assert s3.target_url == "https://www.tradingview.com/news-flow/?watchlist=777777"


