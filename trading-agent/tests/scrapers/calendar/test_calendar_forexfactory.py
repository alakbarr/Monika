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
        
        events = scraper.fetch_events(prefer_feed=False)
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
        
        events = scraper.fetch_events(prefer_feed=False)
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

    @patch("scrapers.calendar.calendar_forexfactory.BaseScraper._initialize_browser")
    @patch("scrapers.calendar.calendar_forexfactory.ForexFactoryCalendarScraper._load_from_cache", return_value=None)
    @patch("scrapers.calendar.calendar_forexfactory.ForexFactoryCalendarScraper._save_to_cache")
    @patch("scrapers.calendar.calendar_forexfactory.urllib.request.urlopen")
    def test_fetch_feed_events_success(self, mock_urlopen, mock_save, mock_load, mock_init):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"""[
            {
                "title": "Non-Farm Employment Change",
                "country": "USD",
                "date": "2026-09-25T08:30:00-04:00",
                "impact": "High",
                "forecast": "150K",
                "previous": "142K"
            },
            {
                "title": "ECB Monetary Policy Statement",
                "country": "EUR",
                "date": "2026-09-25T07:45:00-04:00",
                "impact": "Medium",
                "forecast": "",
                "previous": ""
            }
        ]"""
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        scraper = ForexFactoryCalendarScraper()
        events = scraper.fetch_events(prefer_feed=True)
        assert len(events) == 2
        assert events[0].event_name == "Non-Farm Employment Change"
        assert events[0].currency == "USD"
        assert events[0].impact == "High"
        assert events[0].forecast == "150K"
        assert events[0].previous == "142K"
        assert events[0].time == "2026-09-25T12:30:00Z"
        assert events[0].country == "US"

        assert events[1].event_name == "ECB Monetary Policy Statement"
        assert events[1].currency == "EUR"
        assert events[1].impact == "Medium"
        assert events[1].forecast is None

    @patch("scrapers.calendar.calendar_forexfactory.BaseScraper._initialize_browser")
    def test_fetch_feed_from_cache_hit(self, mock_init):
        scraper = ForexFactoryCalendarScraper()
        cached_data = [
            {
                "title": "Cached Event",
                "country": "GBP",
                "date": "2026-09-25T10:00:00-04:00",
                "impact": "Low",
                "forecast": "1.0%",
                "previous": "0.8%"
            }
        ]
        with patch.object(scraper, "_load_from_cache", return_value=cached_data):
            events = scraper.fetch_events(prefer_feed=True)
            assert len(events) == 1
            assert events[0].event_name == "Cached Event"
            assert events[0].currency == "GBP"
            assert events[0].country == "GB"

