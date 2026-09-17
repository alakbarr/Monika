import pytest
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from scrapers.social.twitter_watch import TwitterWatchScraper
from datetime import datetime, timezone, timedelta

class TestTwitterWatchScraper:
    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_load_cookies_success(self, mock_init, tmp_path):
        scraper = TwitterWatchScraper()
        
        cookie_file = tmp_path / "test_cookies.json"
        cookie_file.write_text('[{"name": "test", "value": "1"}]')
        
        cookies = scraper._load_cookies(str(cookie_file))
        assert any(c.get("name") == "test" and c.get("value") == "1" for c in cookies)
        assert any(c.get("name") == "lang" and c.get("value") == "en" for c in cookies)

    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_load_cookies_forces_lang_en_from_id(self, mock_init, tmp_path):
        scraper = TwitterWatchScraper()
        
        # Test dict format with lang=id
        dict_cookie_file = tmp_path / "dict_cookies.json"
        dict_cookie_file.write_text('{"auth_token": "abc123xyz", "lang": "id"}')
        
        cookies_dict = scraper._load_cookies(str(dict_cookie_file))
        assert isinstance(cookies_dict, dict)
        assert cookies_dict["lang"] == "en"

        # Test list format with lang=id
        list_cookie_file = tmp_path / "list_cookies.json"
        list_cookie_file.write_text('[{"name": "lang", "value": "id", "domain": ".x.com"}]')
        
        cookies_list = scraper._load_cookies(str(list_cookie_file))
        assert isinstance(cookies_list, list)
        assert cookies_list[0]["value"] == "en"

    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_pick_session_no_sessions(self, mock_init, tmp_path):
        scraper = TwitterWatchScraper()
        scraper.session_dir = tmp_path
        
        session = scraper._pick_session()
        assert session is None

    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_pick_session_with_sessions(self, mock_init, tmp_path):
        scraper = TwitterWatchScraper()
        scraper.session_dir = tmp_path
        scraper.rotation_state_file = tmp_path / "twitter_pool_state.json"
        scraper.quarantined_file = tmp_path / "twitter_quarantined.json"
        
        # Create fake sessions
        (tmp_path / "twitter_session_1.json").touch()
        (tmp_path / "twitter_session_2.json").touch()
        
        # Quarantine session 1
        with open(scraper.quarantined_file, "w") as f:
            json.dump([str(tmp_path / "twitter_session_1.json")], f)
            
        session = scraper._pick_session()
        assert session == str(tmp_path / "twitter_session_2.json")
        
        # rotation state updated
        with open(scraper.rotation_state_file, "r") as f:
            state = json.load(f)
            assert str(tmp_path / "twitter_session_2.json") in state["used"]

    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_fetch_latest_tweets_no_session(self, mock_init):
        scraper = TwitterWatchScraper()
        scraper._pick_session = MagicMock(return_value=None)
        
        tweets = scraper.fetch_latest_tweets()
        assert tweets == []

    @patch("scrapers.social.twitter_watch.BaseScraper._initialize_browser")
    def test_fetch_latest_tweets_success(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = TwitterWatchScraper()
        scraper._pick_session = MagicMock(return_value="test_session.json")
        scraper._load_cookies = MagicMock(return_value=[{"name": "test"}])
        
        mock_page.url = "https://x.com/home"
        mock_page.eles.return_value = [] # no login prompt
        mock_page.wait.ele_displayed.return_value = True # articles found
        
        # Mock article HTML
        mock_article = MagicMock()
        now_iso = datetime.now(timezone.utc).isoformat()
        mock_article.html = f'''
        <article>
            <a href="/testuser/status/123456">Link</a>
            <time datetime="{now_iso}"></time>
            <div data-testid="User-Name"><span>@testuser</span></div>
            <div data-testid="tweetText">Hello world</div>
            <div data-testid="tweetPhoto"><img src="http://img.com/1.jpg"></div>
        </article>
        '''
        
        # Second call to page.eles("tag:article") returns the article, third returns empty (so it breaks loop early for testing)
        # Actually it loops max_scrolls times, let's just make consecutive_old trigger
        old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        mock_old = MagicMock()
        mock_old.html = f'''
        <article>
            <a href="/testuser/status/111111">Link</a>
            <time datetime="{old_time}"></time>
        </article>
        '''
        
        mock_page.eles.side_effect = [
            [], # sign in check
            [mock_article, mock_old, mock_old, mock_old, mock_old, mock_old, mock_old], # 1 good, 6 old -> consecutive_old > 5 breaks loop
        ]
        
        # Avoid sleeping
        with patch("time.sleep"):
            tweets = scraper.fetch_latest_tweets()
            
        assert len(tweets) == 1
        assert tweets[0].username == "testuser"
        assert tweets[0].content == "Hello world"
        assert tweets[0].media_urls == ["http://img.com/1.jpg"]
        assert tweets[0].url == "https://x.com/testuser/status/123456"
