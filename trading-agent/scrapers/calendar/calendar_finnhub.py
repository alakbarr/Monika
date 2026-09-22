# ==============================================================================
# File: scrapers/calendar/calendar_finnhub.py
# ==============================================================================
"""
Kalender Ekonomi Finnhub — sumber cadangan jika InvestingCalendarScraper gagal.

Menggunakan endpoint /calendar/economic gratis (tidak perlu scraping, batas 60 request/menit).
Menghindari kegagalan tunggal dari Investing.com untuk memblokir trading saat berita berisiko tinggi.

Penggunaan:
    scraper = FinnhubCalendarScraper()
    events = scraper.fetch_today_events()

Env:
    FINNHUB_API_KEY — Wajib (dapatkan di finnhub.io).
"""

import asyncio
import logging
import os
import time
from datetime import date, timedelta
from typing import List
import aiohttp

from utils.api.http_retry import _CIRCUIT_BREAKER

logger = logging.getLogger("TradingAgent.FinnhubCalendar")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore
    HAS_REQUESTS = False
    logger.warning("requests not installed — FinnhubCalendarScraper unavailable")

from scrapers.models import CalendarEvent


# Pemetaan dampak Finnhub ke sistem 3 level kita
_IMPACT_MAP = {
    "high":   "High",
    "medium": "Medium",
    "low":    "Low",
    "na":     "Low",
}

COUNTRY_TO_CURRENCY = {
    "US": "USD", "USA": "USD", "EZ": "EUR", "EU": "EUR", "EMU": "EUR", "DE": "EUR", "FR": "EUR", "IT": "EUR",
    "GB": "GBP", "UK": "GBP", "JP": "JPY", "JPN": "JPY", "AU": "AUD", "AUS": "AUD",
    "CA": "CAD", "CAN": "CAD", "CH": "CHF", "NZ": "NZD", "CN": "CNY"
}


class FinnhubCalendarScraper:
    """
    Mengambil data kalender ekonomi dari API Finnhub.
    Sesuai dengan interface InvestingCalendarScraper: fetch_today_events().
    """

    BASE_URL = "https://finnhub.io/api/v1/calendar/economic"
    _endpoint_403_detected = False

    def __init__(self, api_key: str | None = None, days_ahead: int = 2):
        if not api_key and not os.getenv("FINNHUB_API_KEY"):
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except Exception:
                pass
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
        self.days_ahead = days_ahead

    def fetch_today_events(self) -> List[CalendarEvent]:
        """Mengambil berita ekonomi hari ini sampai days_ahead."""
        if not HAS_REQUESTS or requests is None:
            logger.error("requests library not installed — cannot use FinnhubCalendarScraper")
            return []

        if not self.api_key:
            logger.warning("FINNHUB_API_KEY not set — FinnhubCalendarScraper disabled")
            return []

        if FinnhubCalendarScraper._endpoint_403_detected:
            logger.debug("Finnhub economic calendar requires paid plan — skipping request.")
            return []

        today = date.today()
        # Awal minggu ini (Senin)
        start_date = today - timedelta(days=today.weekday())
        # Akhir minggu depan (Minggu)
        end = start_date + timedelta(days=13)

        domain = "finnhub.io"
        if domain in _CIRCUIT_BREAKER and time.time() < _CIRCUIT_BREAKER[domain]:
            logger.warning(f"Circuit breaker OPEN for {domain}, skipping Finnhub calendar fetch")
            return []

        data = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(
                    self.BASE_URL,
                    params={
                        "from":   start_date.isoformat(),
                        "to":     end.isoformat(),
                        "token":  self.api_key,
                    },
                    timeout=15,
                )
                if resp.status_code == 403:
                    if not FinnhubCalendarScraper._endpoint_403_detected:
                        FinnhubCalendarScraper._endpoint_403_detected = True
                        logger.info(f"Finnhub economic calendar endpoint returned 403 Forbidden (requires paid subscription plan) — disabling Finnhub calendar endpoint for this session")
                    else:
                        logger.debug("Finnhub calendar 403: Forbidden")
                    return []

                if resp.status_code == 429:
                    _CIRCUIT_BREAKER[domain] = time.time() + 60.0
                    logger.warning(f"Finnhub rate limited (429), circuit breaker set for {domain}")
                    time.sleep(2.0 * (attempt + 1))
                    continue

                if resp.status_code in (500, 502, 503, 504):
                    logger.warning(f"Finnhub server error {resp.status_code}, retry {attempt+1}/{max_retries}")
                    time.sleep(1.0 * (2 ** attempt))
                    continue

                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                logger.warning(f"Finnhub calendar fetch attempt {attempt+1}/{max_retries} failed: {e}")
                time.sleep(1.0 * (2 ** attempt))

        if data is None:
            logger.error("Finnhub calendar fetch failed after all retries")
            _CIRCUIT_BREAKER[domain] = time.time() + 60.0
            return []

        events = self._parse_events(data.get("economicCalendar", []))
        logger.info(f"FinnhubCalendarScraper: fetched {len(events)} events ({today} to {end})")
        try:
            from data_sources.circuit_breaker import record_feed_heartbeat
            record_feed_heartbeat("finnhub", metadata={"events_count": len(events)})
            record_feed_heartbeat("economic_calendar", metadata={"source": "finnhub", "events_count": len(events)})
        except Exception:
            pass
        return events

    def _parse_events(self, events_raw: list) -> List[CalendarEvent]:
        """Parse raw Finnhub calendar JSON records into CalendarEvent models."""
        events: List[CalendarEvent] = []
        for item in events_raw:
            try:
                ev = CalendarEvent(
                    event_name=item.get("event", "Unknown Event"),
                    time=item.get("time", ""),
                    currency=COUNTRY_TO_CURRENCY.get((item.get("country") or "").upper(), (item.get("country") or "").upper() or "USD"),
                    impact=_IMPACT_MAP.get(str(item.get("impact", "low")).lower(), "Low"),
                    actual=str(item.get("actual", "")) if item.get("actual") is not None else None,
                    forecast=str(item.get("estimate", "")) if item.get("estimate") is not None else None,
                    previous=str(item.get("prev", "")) if item.get("prev") is not None else None,
                    country=(item.get("country") or "").upper() or None,
                )
                events.append(ev)
            except Exception as parse_err:
                logger.debug(f"Failed to parse Finnhub event: {parse_err} — item={item}")
                continue
        return events

    async def afetch_today_events(self) -> List[CalendarEvent]:
        """
        Mengambil berita ekonomi hari ini sampai days_ahead secara non-blocking (async).
        Menggunakan aiohttp dan asyncio.sleep untuk mencegah blocking pada event loop (H-19).
        """
        if not self.api_key:
            logger.warning("FINNHUB_API_KEY not set — FinnhubCalendarScraper disabled")
            return []

        if FinnhubCalendarScraper._endpoint_403_detected:
            logger.debug("Finnhub economic calendar requires paid plan — skipping request.")
            return []

        today = date.today()
        start_date = today - timedelta(days=today.weekday())
        end = start_date + timedelta(days=13)

        domain = "finnhub.io"
        if domain in _CIRCUIT_BREAKER and time.time() < _CIRCUIT_BREAKER[domain]:
            logger.warning(f"Circuit breaker OPEN for {domain}, skipping Finnhub calendar fetch")
            return []

        data = None
        max_retries = 3
        timeout = aiohttp.ClientTimeout(total=15)

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    params = {
                        "from": start_date.isoformat(),
                        "to": end.isoformat(),
                        "token": self.api_key,
                    }
                    async with session.get(self.BASE_URL, params=params) as resp:
                        if resp.status == 403:
                            if not FinnhubCalendarScraper._endpoint_403_detected:
                                FinnhubCalendarScraper._endpoint_403_detected = True
                                logger.info(
                                    "Finnhub economic calendar endpoint returned 403 Forbidden (requires paid subscription plan) — disabling Finnhub calendar endpoint for this session"
                                )
                            else:
                                logger.debug("Finnhub calendar 403: Forbidden")
                            return []

                        if resp.status == 429:
                            _CIRCUIT_BREAKER[domain] = time.time() + 60.0
                            logger.warning(f"Finnhub rate limited (429), circuit breaker set for {domain}")
                            await asyncio.sleep(2.0 * (attempt + 1))
                            continue

                        if resp.status in (500, 502, 503, 504):
                            logger.warning(f"Finnhub server error {resp.status}, retry {attempt+1}/{max_retries}")
                            await asyncio.sleep(1.0 * (2 ** attempt))
                            continue

                        resp.raise_for_status()
                        data = await resp.json()
                        break
            except Exception as e:
                logger.warning(f"Finnhub async calendar fetch attempt {attempt+1}/{max_retries} failed: {e}")
                await asyncio.sleep(1.0 * (2 ** attempt))

        if data is None:
            logger.error("Finnhub async calendar fetch failed after all retries")
            _CIRCUIT_BREAKER[domain] = time.time() + 60.0
            return []

        events = self._parse_events(data.get("economicCalendar", []))
        logger.info(f"FinnhubCalendarScraper (async): fetched {len(events)} events ({today} to {end})")
        try:
            from data_sources.circuit_breaker import record_feed_heartbeat
            record_feed_heartbeat("finnhub", metadata={"events_count": len(events)})
            record_feed_heartbeat("economic_calendar", metadata={"source": "finnhub", "events_count": len(events)})
        except Exception:
            pass
        return events

    # Uniform interface aliases matching InvestingCalendarScraper & ForexfactoryCalendarScraper
    fetch_events = fetch_today_events
    afetch_events = afetch_today_events
