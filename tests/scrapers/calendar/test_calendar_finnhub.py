"""
Unit tests for FinnhubCalendarScraper asynchronous scraping (H-19).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scrapers.calendar.calendar_finnhub import FinnhubCalendarScraper


@pytest.fixture(autouse=True)
def reset_endpoint_flag():
    from utils.api.http_retry import _CIRCUIT_BREAKER
    FinnhubCalendarScraper._endpoint_403_detected = False
    FinnhubCalendarScraper._endpoint_403_until = 0.0
    _CIRCUIT_BREAKER.pop("finnhub.io", None)
    yield
    FinnhubCalendarScraper._endpoint_403_detected = False
    FinnhubCalendarScraper._endpoint_403_until = 0.0
    _CIRCUIT_BREAKER.pop("finnhub.io", None)


@pytest.mark.asyncio
async def test_finnhub_afetch_today_events_success():
    scraper = FinnhubCalendarScraper(api_key="test_finnhub_key")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={
        "economicCalendar": [
            {
                "event": "US Non-Farm Payrolls",
                "time": "2026-09-15 12:30:00",
                "country": "US",
                "impact": "high",
                "actual": "220k",
                "estimate": "200k",
                "prev": "180k",
            }
        ]
    })

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_ctx

        events = await scraper.afetch_today_events()

        assert len(events) == 1
        ev = events[0]
        assert ev.event_name == "US Non-Farm Payrolls"
        assert ev.currency == "USD"
        assert ev.impact == "High"
        assert ev.actual == "220k"


@pytest.mark.asyncio
async def test_finnhub_afetch_today_events_403():
    scraper = FinnhubCalendarScraper(api_key="test_finnhub_key")
    FinnhubCalendarScraper._endpoint_403_detected = False

    mock_resp = MagicMock()
    mock_resp.status = 403

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_ctx

        events = await scraper.afetch_today_events()
        assert len(events) == 0
        assert FinnhubCalendarScraper._endpoint_403_detected is True
