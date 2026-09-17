import pytest
from unittest.mock import MagicMock, patch
from scrapers.calendar.calendar_forexfactory import ForexFactoryCalendarScraper
from database.adapters import parse_timestamp

class TestForexFactoryCalendarScraper:
    @patch("scrapers.calendar.calendar_forexfactory.BaseScraper._initialize_browser")
    def test_fetch_events_fail_navigate(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        
        scraper = ForexFactoryCalendarScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=False)
        
        events = scraper.fetch_events()
        assert events == []
        assert scraper.navigate_with_fallback.call_count == 2

    @patch("scrapers.calendar.calendar_forexfactory.BaseScraper._initialize_browser")
    def test_fetch_events_success_with_utc_normalization(self, mock_init):
        mock_page = MagicMock()
        mock_init.return_value = mock_page
        mock_page.html = """
        <table class="calendar__table">
            <tr class="calendar__row calendar__row--new-day">
                <td class="calendar__date"><span class="date">Thu Aug 27</span></td>
                <td class="calendar__time">8:30am</td>
                <td class="calendar__currency">USD</td>
                <td class="calendar__impact"><span class="icon--ff-impact-red"></span></td>
                <td class="calendar__event">Initial Jobless Claims</td>
                <td class="calendar__actual">228K</td>
                <td class="calendar__forecast">230K</td>
                <td class="calendar__previous">235K</td>
            </tr>
        </table>
        """
        
        scraper = ForexFactoryCalendarScraper()
        scraper.navigate_with_fallback = MagicMock(return_value=True)
        scraper.page = mock_page
        
        events = scraper.fetch_events()
        assert len(events) == 2  # once per url
        event = events[0]
        assert event.event_name == "Initial Jobless Claims"
        assert event.currency == "USD"
        assert event.impact == "High"
        
        # 8:30am EDT (America/New_York) -> 12:30:00 UTC
        dt = parse_timestamp(event.time)
        assert dt is not None
        assert dt.tzname() == "UTC"
        assert dt.hour == 12
        assert dt.minute == 30
