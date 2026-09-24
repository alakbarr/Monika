import pytest
from unittest.mock import MagicMock, patch
from scrapers.calendar.calendar_investing import InvestingCalendarScraper

class TestInvestingCalendarScraper:
    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_fetch_events_fail_navigate(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = InvestingCalendarScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=False)
        
        events = scraper.fetch_events()
        assert events == []
        scraper.navigate_with_fallback.assert_called_once()

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_fetch_events_no_table(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = InvestingCalendarScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=True)
        
        mock_page.ele.return_value = None # Table not found
        
        events = scraper.fetch_events()
        assert events == []

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_fetch_events_success(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = InvestingCalendarScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=True)
        
        # Mock popup element (not found)
        mock_page.ele.side_effect = lambda sel, timeout: None if "sign-up" in sel else MagicMock(
            inner_html="""
            <table>
                <tr>
                    <td>Check</td>
                    <td>10:00</td>
                    <td>US</td>
                    <td>NFP Act:100</td>
                    <td>opacity-20</td> <!-- 1 star muted -> Medium -->
                    <td>100K</td>
                    <td>90K</td>
                    <td>80K</td>
                </tr>
                <tr>
                    <td>Check</td>
                    <td>14:00</td>
                    <td>EU</td>
                    <td>ECB Rate</td>
                    <td></td> <!-- 0 stars muted -> High -->
                    <td>-</td>
                    <td>-</td>
                    <td>-</td>
                </tr>
            </table>
            """
        )
        
        events = scraper.fetch_events()
        assert len(events) == 2
        
        from database.adapters import parse_timestamp
        dt0 = parse_timestamp(events[0].time)
        assert dt0 is not None
        assert dt0.tzname() == "UTC"
        assert events[0].currency == "USD"
        assert events[0].event_name == "NFP"
        assert events[0].impact == "Medium"
        assert events[0].actual == "100K"
        
        dt1 = parse_timestamp(events[1].time)
        assert dt1 is not None
        assert dt1.tzname() == "UTC"
        assert events[1].currency == "EUR"
        assert events[1].event_name == "ECB Rate"
        assert events[1].impact == "High"
        assert events[1].actual is None
        assert events[1].forecast is None

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_apply_time_filter_button_success(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        mock_btn = MagicMock()
        mock_btn.states.is_displayed = True
        mock_page.ele.return_value = mock_btn

        scraper = InvestingCalendarScraper()
        res = scraper._apply_time_filter_human_like("This Week")
        assert res is True
        mock_btn.click.assert_called_once_with(by_js=True)

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_apply_time_filter_custom_picker_fallback(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page

        mock_custom_btn = MagicMock()
        mock_custom_btn.states.is_displayed = True
        
        mock_container = MagicMock()
        mock_input1 = MagicMock()
        mock_input2 = MagicMock()
        mock_container.eles.return_value = [mock_input1, mock_input2]
        
        mock_apply_btn = MagicMock()

        def fake_ele(sel, timeout=None):
            if "tag:button@@text():This Week" in sel or "xpath://button" in sel and "This Week" in sel:
                return None
            if "Custom dates" in sel or "Custom" in sel:
                return mock_custom_btn
            if "DateRangePicker" in sel:
                return mock_container
            if "Apply" in sel:
                return mock_apply_btn
            return None

        mock_page.ele.side_effect = fake_ele
        mock_page.listen.wait.return_value = True

        scraper = InvestingCalendarScraper()
        res = scraper._apply_time_filter_human_like("This Week")
        assert res is True
        mock_apply_btn.click.assert_called_once_with(by_js=True)

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_investing_scraper_initializes_with_eager_and_no_imgs(self, mock_init):
        scraper = InvestingCalendarScraper()
        assert scraper.load_mode == "eager"
        assert scraper.no_imgs is True

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_find_calendar_table_priority(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        mock_table = MagicMock()
        mock_page.ele.return_value = mock_table

        scraper = InvestingCalendarScraper()
        tbl = scraper._find_calendar_table()
        assert tbl == mock_table
        # Verify first call checked modern xpath selector with short timeout
        first_call = mock_page.ele.call_args_list[0]
        assert "datatable" in first_call[0][0]
        assert first_call[1]["timeout"] == 0.5

    @patch("scrapers.calendar.calendar_investing.BaseScraper._initialize_browser")
    def test_load_all_calendar_rows_uses_fast_js_count(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        mock_table = MagicMock()
        mock_page.ele.return_value = mock_table
        mock_page.run_js.return_value = 50

        scraper = InvestingCalendarScraper()
        scraper._load_all_calendar_rows()
        # Verify run_js was used to query tr count efficiently
        assert mock_page.run_js.called


