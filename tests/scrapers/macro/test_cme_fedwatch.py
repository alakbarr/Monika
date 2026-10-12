import pytest
from unittest.mock import MagicMock, patch
from scrapers.macro.cme_fedwatch import FedWatchScraper

class TestFedWatchScraper:
    @patch("scrapers.macro.cme_fedwatch.BaseScraper._initialize_browser")
    @patch("time.sleep", return_value=None)
    def test_fetch_probabilities_success(self, mock_sleep, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = FedWatchScraper()
        
        # Mock iframe
        mock_iframe = MagicMock()
        mock_page.get_frame.return_value = mock_iframe
        
        # Mock tabs: only return 1 tab
        mock_tab = MagicMock()
        mock_tab.text = "Sep 16, 2026"
        
        def mock_ele(selector, timeout=None):
            if "ctrl0" in selector:
                return mock_tab
            return None
            
        mock_iframe.ele.side_effect = mock_ele
        
        # Mock HTML
        mock_iframe.html = """
        <html>
            <table></table>
            <table></table>
            <table></table>
            <table></table>
            <table>
                <tr>
                    <td>5.25-5.50 (Current)</td>
                    <td>10.0%</td>
                    <td></td>
                    <td></td>
                    <td></td>
                </tr>
                <tr>
                    <td>5.00-5.25</td>
                    <td>60.0%</td>
                    <td></td>
                    <td></td>
                    <td></td>
                </tr>
                <tr>
                    <td>5.25-5.50</td>
                    <td>40.0%</td>
                    <td></td>
                    <td></td>
                    <td></td>
                </tr>
            </table>
        </html>
        """
        
        meetings = scraper.fetch_probabilities()
        
        assert len(meetings) == 1
        meeting = meetings[0]
        assert meeting.meeting_date == "Sep 16, 2026"
        assert meeting.current_rate_ref == 0.06
        assert "HOLD (60.0%)" in meeting.most_likely
        assert len(meeting.probabilities) == 3
        
    @patch("scrapers.macro.cme_fedwatch.BaseScraper._initialize_browser")
    def test_fetch_probabilities_no_iframe(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = FedWatchScraper()
        
        # Mock iframe locator to return None immediately
        with patch.object(scraper, "_locate_quikstrike_iframe", return_value=None):
            meetings = scraper.fetch_probabilities()
            assert len(meetings) == 0

    @patch("scrapers.macro.cme_fedwatch.BaseScraper._initialize_browser")
    @patch("time.sleep", return_value=None)
    def test_fetch_probabilities_dynamic_table_detection(self, mock_sleep, mock_init):
        """Verify dynamic table detection works when table is at index 0 with TARGET RATE header."""
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        scraper = FedWatchScraper()

        mock_iframe = MagicMock()
        mock_page.get_frame.return_value = mock_iframe
        mock_tab = MagicMock()
        mock_tab.text = "Nov 05, 2026"
        mock_iframe.ele.side_effect = lambda sel, timeout=None: mock_tab if "ctrl0" in sel else None

        # Table is first table (index 0), has TARGET RATE and PROBABILITY header
        mock_iframe.html = """
        <html>
            <table>
                <thead>
                    <tr><th>TARGET RATE</th><th>PROBABILITY</th><th>PRIOR DAY</th><th>1 WEEK</th><th>1 MONTH</th></tr>
                </thead>
                <tbody>
                    <tr><td>4.50-4.75 (Current)</td><td>20.0%</td><td></td><td></td><td></td></tr>
                    <tr><td>4.25-4.50</td><td>80.0%</td><td></td><td></td><td></td></tr>
                </tbody>
            </table>
        </html>
        """
        meetings = scraper.fetch_probabilities()
        assert len(meetings) == 1
        assert meetings[0].meeting_date == "Nov 05, 2026"
        assert len(meetings[0].probabilities) == 2
        assert "HOLD (80.0%)" in meetings[0].most_likely

    @patch("scrapers.macro.cme_fedwatch.BaseScraper._initialize_browser")
    @patch("time.sleep", return_value=None)
    def test_fetch_probabilities_dynamic_rate_fallback(self, mock_sleep, mock_init):
        """Verify dynamic rate is fetched when table has no (Current) marker."""
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        scraper = FedWatchScraper()

        mock_iframe = MagicMock()
        mock_page.get_frame.return_value = mock_iframe
        mock_tab = MagicMock()
        mock_tab.text = "Dec 16, 2026"
        mock_iframe.ele.side_effect = lambda sel, timeout=None: mock_tab if "ctrl0" in sel else None

        # Table has no (Current)
        mock_iframe.html = """
        <html>
            <table>
                <tr><th>TARGET RATE</th><th>PROBABILITY</th><th>X</th><th>Y</th><th>Z</th></tr>
                <tr><td>4.75-5.00</td><td>15.0%</td><td></td><td></td><td></td></tr>
                <tr><td>4.50-4.75</td><td>85.0%</td><td></td><td></td><td></td></tr>
            </table>
        </html>
        """
        # Patch fallback policy rate to 4.75% (0.0475)
        with patch.object(scraper, "_get_fallback_policy_rate", return_value=0.0475):
            meetings = scraper.fetch_probabilities()
            assert len(meetings) == 1
            assert meetings[0].meeting_date == "Dec 16, 2026"
            assert meetings[0].current_rate_ref == 0.05
            assert len(meetings[0].probabilities) == 2

