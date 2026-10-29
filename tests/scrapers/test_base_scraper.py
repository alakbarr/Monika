import pytest
from unittest.mock import MagicMock, patch, ANY
from monika.infrastructure.data_ingestion.scrapers.base_scraper import BaseScraper


class TestBaseScraper:
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
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

    @patch.object(BaseScraper, "_cleanup_stale_profile_locks")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_init_profile(self, mock_options, mock_page, mock_cleanup):
        scraper = BaseScraper(headless=False, profile_name="test_profile")

        assert not scraper.headless
        assert scraper.profile_name == "test_profile"

        mock_options_instance = mock_options.return_value
        mock_options_instance.headless.assert_called_with(False)
        # Verify user data path is set
        assert mock_options_instance.set_user_data_path.called
        assert mock_cleanup.called

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
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

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
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
            assert not scraper.headless  # Fallback switches headless to False
            mock_init.assert_called_with(False, port=ANY)

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_navigate_handles_searchid_keyerror_and_recovers(self, mock_options, mock_page):
        scraper = BaseScraper(headless=True)

        mock_wait = MagicMock()
        mock_wait.ele_displayed.side_effect = KeyError("searchId")
        scraper.page.wait = mock_wait

        mock_ele = MagicMock()
        scraper.page.ele.return_value = mock_ele

        res = scraper.navigate_with_fallback("http://test.com", "div.content")

        assert res is True
        scraper.page.ele.assert_called_with("div.content", timeout=2)

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_navigate_handles_searchid_keyerror_and_fails_if_ele_missing(self, mock_options, mock_page):
        scraper = BaseScraper(headless=True)

        mock_wait = MagicMock()
        mock_wait.ele_displayed.side_effect = KeyError("searchId")
        scraper.page.wait = mock_wait
        scraper.page.ele.return_value = None
        scraper.page.html = "<html><body>No element here</body></html>"

        with patch.object(scraper, "_fallback", return_value=False) as mock_fallback:
            res = scraper.navigate_with_fallback("http://test.com", "div.content")
            assert res is False
            mock_fallback.assert_called_once_with("http://test.com", "div.content")

    def test_drissionpage_cdp_search_patch_behavior(self):
        from DrissionPage._elements.none_element import NoneElement
        from DrissionPage._pages.chromium_base import ChromiumBase

        class DummyBase(ChromiumBase):
            def __init__(self):
                self._none_ele_value = None
                self._none_ele_return_value = False

        dummy = DummyBase()

        # Save current _find_elements
        orig_method = ChromiumBase._find_elements

        def mock_broken_find(self, *args, **kwargs):
            raise KeyError("searchId")

        try:
            # Re-wrap with test mock to simulate DrissionPage CDP failure
            ChromiumBase._find_elements = mock_broken_find
            from monika.infrastructure.data_ingestion import scrapers
            import monika.infrastructure.data_ingestion.scrapers.base_scraper as bs_mod

            bs_mod._DRISSIONPAGE_SEARCH_PATCHED = False
            bs_mod._apply_drissionpage_cdp_search_patch()

            # Test single element lookup (index=1) returns NoneElement
            result_single = dummy._find_elements("div.test", timeout=1, index=1)
            assert isinstance(result_single, NoneElement)

            # Test multiple elements lookup (index=None) returns empty list
            result_multi = dummy._find_elements("div.test", timeout=1, index=None)
            assert result_multi == []

            # Other KeyError should still raise
            def mock_other_keyerror(self, *args, **kwargs):
                raise KeyError("other_key")

            ChromiumBase._find_elements = mock_other_keyerror
            bs_mod._DRISSIONPAGE_SEARCH_PATCHED = False
            bs_mod._apply_drissionpage_cdp_search_patch()

            with pytest.raises(KeyError, match="other_key"):
                dummy._find_elements("div.test", timeout=1)
        finally:
            ChromiumBase._find_elements = orig_method

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_close(self, mock_options, mock_page):
        scraper = BaseScraper()
        scraper.close()
        scraper.page.quit.assert_called_once()

        # Test exception catching
        scraper.page.quit.side_effect = Exception("Test")
        scraper.close()  # should not raise

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.kill_process_tree")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_close_kills_browser_pid(self, mock_options, mock_page, mock_kill):
        mock_page_inst = mock_page.return_value
        mock_page_inst.process_id = 12345
        scraper = BaseScraper()
        assert scraper.browser_pid == 12345
        scraper.close()
        mock_kill.assert_called_once_with(12345)
        assert scraper.browser_pid is None

    def test_kill_process_tree_invalid_inputs(self):
        from monika.infrastructure.data_ingestion.scrapers.base_scraper import kill_process_tree

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
        from monika.infrastructure.data_ingestion.scrapers.base_scraper import kill_process_tree

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
        from monika.infrastructure.data_ingestion.scrapers.base_scraper import kill_process_tree

        res = kill_process_tree(8888)
        assert res is True
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args[0][0]
        assert cmd == ["taskkill", "/F", "/T", "/PID", "8888"]

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.kill_process_tree")
    @patch("psutil.process_iter")
    def test_cleanup_stale_profile_processes(self, mock_proc_iter, mock_kill, tmp_path):
        fake_proc = MagicMock()
        fake_proc.pid = 7777
        fake_proc.info = {"name": "chrome.exe", "cmdline": ["chrome.exe", f"--user-data-dir={tmp_path}"]}
        mock_proc_iter.return_value = [fake_proc]

        BaseScraper._cleanup_stale_profile_locks(tmp_path)
        mock_kill.assert_called_once_with(7777)

    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.kill_process_tree")
    @patch("psutil.process_iter")
    def test_cleanup_stale_profile_processes_skips_active_pids(self, mock_proc_iter, mock_kill, tmp_path):
        from monika.infrastructure.data_ingestion.scrapers.base_scraper import (
            _ACTIVE_BROWSER_PIDS,
            _PROFILE_LOCKS_GUARD,
        )

        # Active direct PID
        fake_proc_active = MagicMock()
        fake_proc_active.pid = 9991
        fake_proc_active.ppid.return_value = 1
        fake_proc_active.info = {"name": "chrome.exe", "cmdline": ["chrome.exe", f"--user-data-dir={tmp_path}"]}

        # Active child whose parent is in active PIDs
        fake_proc_child = MagicMock()
        fake_proc_child.pid = 9992
        fake_proc_child.ppid.return_value = 9991
        fake_proc_child.info = {"name": "chrome.exe", "cmdline": ["chrome.exe", f"--user-data-dir={tmp_path}"]}

        mock_proc_iter.return_value = [fake_proc_active, fake_proc_child]

        with _PROFILE_LOCKS_GUARD:
            _ACTIVE_BROWSER_PIDS.add(9991)

        try:
            BaseScraper._cleanup_stale_profile_locks(tmp_path)
            mock_kill.assert_not_called()
        finally:
            with _PROFILE_LOCKS_GUARD:
                _ACTIVE_BROWSER_PIDS.discard(9991)

    @patch("pathlib.Path.mkdir")
    @patch.object(BaseScraper, "_cleanup_stale_profile_locks")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumPage")
    @patch("monika.infrastructure.data_ingestion.scrapers.base_scraper.ChromiumOptions")
    def test_profile_lock_lifecycle(self, mock_options, mock_page, mock_cleanup, mock_mkdir):
        scraper = BaseScraper(profile_name="sync_test_profile")
        assert scraper._acquired_profile_lock is True
        assert scraper._profile_lock is not None

        scraper.close()
        assert scraper._acquired_profile_lock is False
        # Multiple close() is idempotent
        scraper.close()
        assert scraper._acquired_profile_lock is False
