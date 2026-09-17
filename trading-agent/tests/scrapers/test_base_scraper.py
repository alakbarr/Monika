import pytest
from unittest.mock import MagicMock, patch, ANY
from scrapers.base_scraper import BaseScraper

class TestBaseScraper:
    @patch("scrapers.base_scraper.ChromiumPage")
    @patch("scrapers.base_scraper.ChromiumOptions")
    def test_init_headless(self, mock_options, mock_page):
        scraper = BaseScraper(headless=True)
        
        assert scraper.headless
        assert scraper.profile_name is None
        
        mock_options_instance = mock_options.return_value
        mock_options_instance.headless.assert_called_with(True)
        assert mock_options_instance.set_user_agent.called
        mock_options_instance.set_argument.assert_any_call("--no-sandbox")
        mock_options_instance.set_argument.assert_any_call("--lang=en-US,en")
        mock_options_instance.set_argument.assert_any_call("--disable-features=Translate")
        mock_options_instance.set_argument.assert_any_call("--disable-translate")
        mock_options_instance.set_pref.assert_any_call("intl.accept_languages", "en-US,en")
        mock_options_instance.set_pref.assert_any_call("translate.enabled", False)
        
        mock_page.assert_called_once_with(mock_options_instance)
        assert scraper.page == mock_page.return_value

    @patch("scrapers.base_scraper.ChromiumPage")
    @patch("scrapers.base_scraper.ChromiumOptions")
    def test_init_profile(self, mock_options, mock_page):
        scraper = BaseScraper(headless=False, profile_name="test_profile")
        
        assert not scraper.headless
        assert scraper.profile_name == "test_profile"
        
        mock_options_instance = mock_options.return_value
        mock_options_instance.headless.assert_called_with(False)
        # Verify user data path is set
        assert mock_options_instance.set_user_data_path.called

    @patch("scrapers.base_scraper.ChromiumPage")
    @patch("scrapers.base_scraper.ChromiumOptions")
    def test_navigate_success(self, mock_options, mock_page):
        scraper = BaseScraper(headless=True)
        
        # Setup page wait mock
        mock_wait = MagicMock()
        mock_wait.ele_displayed.return_value = True
        scraper.page.wait = mock_wait
        
        res = scraper.navigate_with_fallback("http://test.com", "div.content")
        
        assert res is True
        scraper.page.get.assert_called_with("http://test.com")
        mock_wait.ele_displayed.assert_called_with("div.content", timeout=30)

    @patch("scrapers.base_scraper.ChromiumPage")
    def test_navigate_fallback(self, mock_page, monkeypatch):
        monkeypatch.setenv("SCRAPER_ALLOW_GUI_FALLBACK", "true")
        # Allow patch of _initialize_browser to avoid calling real ChromiumPage again
        with patch.object(BaseScraper, "_initialize_browser") as mock_init:
            mock_first_page = MagicMock()
            mock_first_page.get.side_effect = Exception("Connection blocked")
            
            mock_fallback_page = MagicMock()
            mock_fallback_page.wait.ele_displayed.return_value = True
            
            mock_init.side_effect = [mock_first_page, mock_fallback_page]
    
            scraper = BaseScraper(headless=True)
            
            res = scraper.navigate_with_fallback("http://test.com", "div.content")
            
            assert res is True
            assert not scraper.headless # Fallback switches headless to False
            mock_init.assert_called_with(False, port=ANY)

    @patch("scrapers.base_scraper.ChromiumPage")
    @patch("scrapers.base_scraper.ChromiumOptions")
    def test_close(self, mock_options, mock_page):
        scraper = BaseScraper()
        scraper.close()
        scraper.page.quit.assert_called_once()
        
        # Test exception catching
        scraper.page.quit.side_effect = Exception("Test")
        scraper.close() # should not raise

    @patch("scrapers.base_scraper.kill_process_tree")
    @patch("scrapers.base_scraper.ChromiumPage")
    @patch("scrapers.base_scraper.ChromiumOptions")
    def test_close_kills_browser_pid(self, mock_options, mock_page, mock_kill):
        mock_page_inst = mock_page.return_value
        mock_page_inst.process_id = 12345
        scraper = BaseScraper()
        assert scraper.browser_pid == 12345
        scraper.close()
        mock_kill.assert_called_once_with(12345)
        assert scraper.browser_pid is None

    def test_kill_process_tree_invalid_inputs(self):
        from scrapers.base_scraper import kill_process_tree
        assert kill_process_tree(None) is False
        assert kill_process_tree(0) is False
        assert kill_process_tree(-100) is False
        assert kill_process_tree(True) is False
        assert kill_process_tree(False) is False
        assert kill_process_tree("12345") is False
        assert kill_process_tree(MagicMock()) is False

    @patch("psutil.wait_procs")
    @patch("psutil.Process")
    def test_kill_process_tree_psutil(self, mock_proc_cls, mock_wait):
        from scrapers.base_scraper import kill_process_tree
        mock_parent = MagicMock()
        mock_child1 = MagicMock()
        mock_child2 = MagicMock()
        mock_parent.children.return_value = [mock_child1, mock_child2]
        mock_proc_cls.return_value = mock_parent

        res = kill_process_tree(9999)
        assert res is True
        mock_proc_cls.assert_called_once_with(9999)
        mock_child1.kill.assert_called_once()
        mock_child2.kill.assert_called_once()
        mock_parent.kill.assert_called_once()
        mock_wait.assert_called_once()

    @patch("subprocess.run")
    @patch("psutil.Process", side_effect=Exception("psutil error"))
    def test_kill_process_tree_taskkill_fallback(self, mock_proc_cls, mock_subproc, monkeypatch):
        import platform
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        from scrapers.base_scraper import kill_process_tree
        res = kill_process_tree(8888)
        assert res is True
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args[0][0]
        assert cmd == ["taskkill", "/F", "/T", "/PID", "8888"]

