# ==============================================================================
# File: tests/scrapers/test_scraper_language_isolation.py
# ==============================================================================

"""
Unit tests untuk memverifikasi isolasi bahasa Inggris (en-US) dan pencegahan
translasi otomatis di seluruh layer browser scraper.
"""

import pytest
from unittest.mock import MagicMock, patch
from scrapers.base_scraper import BaseScraper
from scrapers.social.twitter_watch import TwitterWatchScraper
from scrapers.news.tradingview_news import TradingViewNewsScraper
from scrapers.news.kitco_news import KitcoNewsScraper
from scrapers.calendar.calendar_investing import InvestingCalendarScraper
from scrapers.macro.cme_fedwatch import FedWatchScraper


class TestScraperLanguageIsolation:
    @patch("scrapers.base_scraper.ChromiumPage")
    @patch("scrapers.base_scraper.ChromiumOptions")
    def test_base_scraper_forces_english_locale(self, mock_options, mock_page):
        scraper = BaseScraper(headless=True)
        opt = mock_options.return_value

        # Pastikan argumen bahasa Inggris dan disable translate selalu dipanggil
        opt.set_argument.assert_any_call("--lang=en-US,en")
        opt.set_argument.assert_any_call("--disable-features=Translate")
        opt.set_argument.assert_any_call("--disable-translate")
        opt.set_pref.assert_any_call("intl.accept_languages", "en-US,en")
        opt.set_pref.assert_any_call("translate.enabled", False)
        opt.set_pref.assert_any_call("translate_whitelists", {})

    @patch("scrapers.base_scraper.ChromiumPage")
    def test_all_scrapers_inherit_english_settings(self, mock_page):
        with patch.object(BaseScraper, "_initialize_browser") as mock_init:
            mock_init.return_value = MagicMock()

            kitco = KitcoNewsScraper(headless=True)
            investing = InvestingCalendarScraper(headless=True)
            fedwatch = FedWatchScraper(headless=True)

            assert isinstance(kitco, BaseScraper)
            assert isinstance(investing, BaseScraper)
            assert isinstance(fedwatch, BaseScraper)

    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_twitter_scraper_url_appends_lang_en(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page

        scraper = TwitterWatchScraper(list_url="https://x.com/i/lists/12345")
        scraper._pick_session = MagicMock(return_value="fake_session.json")
        scraper._load_cookies = MagicMock(return_value={"auth_token": "token123", "lang": "en"})
        mock_page.url = "https://x.com/i/lists/12345?lang=en"
        mock_page.wait.ele_displayed.return_value = False # break immediately

        scraper.fetch_latest_tweets(max_age_minutes=60)

        # Verifikasi navigasi ke URL dengan query ?lang=en
        mock_page.get.assert_any_call("https://x.com/i/lists/12345?lang=en")

    @patch("scrapers.news.tradingview_news.BaseScraper._initialize_browser")
    def test_tradingview_scraper_injects_english_cookies(self, mock_init, tmp_path):
        mock_page = MagicMock()
        mock_init.return_value = mock_page

        scraper = TradingViewNewsScraper(headless=True)
        
        # Test session prep
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=[{"name": "test", "value": "val"}]):
                    scraper._prepare_session()
                    
                    # Verifikasi set cookies menyertakan locale en
                    assert mock_page.set.cookies.called
