import logging
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dateutil import parser as dateutil_parser
from bs4 import BeautifulSoup
from typing import List, Any, Optional

from scrapers.base_scraper import BaseScraper
from scrapers.models import CalendarEvent

logger = logging.getLogger("TradingAgent.ForexFactoryScraper")

class ForexFactoryCalendarScraper(BaseScraper):
    def __init__(self, headless=True, profile_name="ff_calendar"):
        super().__init__(headless, profile_name, load_mode="eager", no_imgs=True)
        self.feed_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self.urls = [
            "https://www.forexfactory.com/calendar?week=this",
            "https://www.forexfactory.com/calendar?week=next"
        ]

    def _get_cache_path(self) -> Path:
        import os
        base_dir = Path(os.getcwd())
        cache_dir = base_dir / "data" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "ff_calendar_thisweek.json"

    def _load_from_cache(self, max_age_seconds: int = 3600) -> Optional[List[dict]]:
        cache_path = self._get_cache_path()
        if not cache_path.exists():
            return None
        try:
            mtime = cache_path.stat().st_mtime
            age = time.time() - mtime
            if age > max_age_seconds:
                logger.debug(f"ForexFactory cache is stale ({age:.0f}s > {max_age_seconds}s)")
                return None
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    logger.info(f"Loaded {len(data)} events from ForexFactory local cache (age: {age/60:.1f}m)")
                    return data
        except Exception as e:
            logger.debug(f"Failed to read ForexFactory cache: {e}")
        return None

    def _save_to_cache(self, raw_items: List[dict]) -> None:
        if not raw_items:
            return
        try:
            cache_path = self._get_cache_path()
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(raw_items, f)
        except Exception as e:
            logger.debug(f"Failed to write ForexFactory cache: {e}")

    def fetch_feed_events(self, max_cache_age: int = 3600, ignore_cache: bool = False) -> List[CalendarEvent]:
        """
        Mengambil peristiwa kalender ekonomi langsung dari feed resmi FairEconomy / ForexFactory JSON.
        Sangat cepat (<0.5s) dan tahan terhadap pemblokiran Cloudflare pada halaman web HTML.
        Dilengkapi caching lokal (TTL default 1 jam, bypassable) untuk mencegah 429 Too Many Requests.
        """
        raw_items = None if ignore_cache else self._load_from_cache(max_age_seconds=max_cache_age)
        
        # 1. Coba via direct HTTP request jika cache tidak ada / kedaluwarsa
        if not raw_items:
            try:
                req = urllib.request.Request(
                    self.feed_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept": "application/json, text/plain, */*",
                    }
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        raw_items = json.loads(resp.read().decode("utf-8"))
                        self._save_to_cache(raw_items)
            except Exception as http_err:
                logger.debug(f"Direct HTTP fetch for FairEconomy feed failed: {http_err}")

        # 2. Coba via browser page jika HTTP gagal (misal 429 atau IP block)
        if not raw_items and hasattr(self, "page") and self.page and not getattr(self, "is_closed", False):
            try:
                page_obj: Any = self.page
                page_obj.get(self.feed_url, timeout=10)
                raw_text = page_obj.run_js("return document.body.innerText")
                if raw_text and raw_text.strip().startswith("["):
                    raw_items = json.loads(raw_text.strip())
                    self._save_to_cache(raw_items)
            except Exception as browser_err:
                logger.debug(f"Browser fetch for FairEconomy feed failed: {browser_err}")

        # 3. Graceful fallback ke cache lama jika ada rate limit (429)
        if not raw_items:
            raw_items = self._load_from_cache(max_age_seconds=86400)
            if raw_items:
                logger.warning(f"ForexFactory feed unavailable — served {len(raw_items)} events from stale cache fallback.")

        if not raw_items:
            return []

        eastern_tz = ZoneInfo("America/New_York")
        events = []
        for item in raw_items:
            raw_date = item.get("date", "")
            try:
                parsed_dt = dateutil_parser.isoparse(raw_date) if hasattr(dateutil_parser, "isoparse") else dateutil_parser.parse(raw_date)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=eastern_tz)
                iso_time = parsed_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                iso_time = raw_date

            raw_impact = item.get("impact", "Low").strip().capitalize()
            impact = raw_impact if raw_impact in ["High", "Medium", "Low"] else "Low"

            currency = item.get("country", "").strip().upper()
            title = item.get("title", "").strip()
            raw_actual = item.get("actual")
            actual = str(raw_actual).strip() if raw_actual is not None and str(raw_actual).strip() != "" else None
            forecast = item.get("forecast") or None
            previous = item.get("previous") or None

            events.append(CalendarEvent(
                time=iso_time,
                currency=currency,
                impact=impact,
                event_name=title,
                actual=actual,
                forecast=forecast if forecast else None,
                previous=previous if previous else None,
                country=currency[:2] if currency else None
            ))

        logger.info(f"ForexFactory (FairEconomy feed): Fetched {len(events)} events (events with actual: {sum(1 for e in events if e.actual)}).")
        return events

    def fetch_events(self, prefer_feed: bool = True, max_cache_age: int = 3600, ignore_cache: bool = False) -> List[CalendarEvent]:
        # 1. Coba ambil dari feed resmi FairEconomy JSON jika diaktifkan (sangat cepat & anti-block)
        if prefer_feed:
            feed_events = self.fetch_feed_events(max_cache_age=max_cache_age, ignore_cache=ignore_cache)
            if feed_events:
                return feed_events

        all_events = []
        for url in self.urls:
            if getattr(self, 'is_closed', False):
                break
            logger.info(f"Navigating to ForexFactory: {url}")
            success = self.navigate_with_fallback(url, 'css:table.calendar__table', timeout=10)
            if not success or getattr(self, 'is_closed', False):
                if not success:
                    logger.warning(f"Failed to load ForexFactory {url} (anti-bot challenge or slow CDN)")
                continue
                
            if not self.page:
                continue
            page_obj: Any = self.page
            page_obj.wait(2)
            html = page_obj.html
            soup = BeautifulSoup(html, "html.parser")
            
            table = soup.find("table", class_="calendar__table")
            if not table:
                logger.warning(f"No calendar table found on {url}")
                continue

            current_time_str = "12:00am"
            current_date_str = datetime.now().strftime("%Y-%m-%d")
            for row in table.find_all("tr", class_="calendar__row"):
                if getattr(self, 'is_closed', False):
                    break
                row_classes = row.get("class")
                row_class_list = row_classes if isinstance(row_classes, list) else [row_classes] if isinstance(row_classes, str) else []
                if "calendar__row--new-day" in row_class_list:
                    # extract date
                    td_date = row.find("td", class_="calendar__date")
                    if td_date:
                        date_span = td_date.find("span", class_="date")
                        if date_span:
                            current_date_str = date_span.get_text(strip=True)
                        else:
                            current_date_str = td_date.get_text(strip=True)
                
                td_time = row.find("td", class_="calendar__time")
                if td_time:
                    t_str = td_time.get_text(strip=True)
                    if t_str and "All Day" not in t_str and "Day" not in t_str:
                        if "am" in t_str.lower() or "pm" in t_str.lower():
                            current_time_str = t_str
                
                full_time_str = f"{current_date_str} {current_time_str}".strip()

                td_currency = row.find("td", class_="calendar__currency")
                if not td_currency:
                    continue
                currency = td_currency.get_text(strip=True)
                
                td_impact = row.find("td", class_="calendar__impact")
                impact = "Low"
                if td_impact:
                    span = td_impact.find("span")
                    if span:
                        cls_attr = span.get("class")
                        cls = cls_attr if isinstance(cls_attr, list) else [cls_attr] if isinstance(cls_attr, str) else []
                        if "icon--ff-impact-red" in cls:
                            impact = "High"
                        elif "icon--ff-impact-ora" in cls:
                            impact = "Medium"
                        elif "icon--ff-impact-yel" in cls:
                            impact = "Low"

                td_event = row.find("td", class_="calendar__event")
                if not td_event:
                    continue
                event_name = td_event.get_text(strip=True)

                td_actual = row.find("td", class_="calendar__actual")
                actual = td_actual.get_text(strip=True) if td_actual else None

                td_forecast = row.find("td", class_="calendar__forecast")
                forecast = td_forecast.get_text(strip=True) if td_forecast else None

                td_previous = row.find("td", class_="calendar__previous")
                previous = td_previous.get_text(strip=True) if td_previous else None

                # Konversi waktu ForexFactory (US Eastern Time) ke UTC ISO format
                from datetime import timezone
                from zoneinfo import ZoneInfo
                from dateutil import parser as dateutil_parser
                eastern_tz = ZoneInfo("America/New_York")
                try:
                    now_ny = datetime.now(eastern_tz)
                    default_dt = datetime(now_ny.year, 1, 1, 0, 0, 0)
                    parsed_dt = dateutil_parser.parse(full_time_str, default=default_dt)
                    if now_ny.month == 12 and parsed_dt.month == 1:
                        parsed_dt = parsed_dt.replace(year=now_ny.year + 1)
                    elif now_ny.month == 1 and parsed_dt.month == 12:
                        parsed_dt = parsed_dt.replace(year=now_ny.year - 1)
                    if parsed_dt.tzinfo is None:
                        parsed_dt = parsed_dt.replace(tzinfo=eastern_tz)
                    iso_utc_time = parsed_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    if current_date_str:
                        import re
                        now_utc = datetime.now(timezone.utc)
                        try:
                            if re.match(r"^\d{4}-\d{2}-\d{2}", current_date_str):
                                iso_utc_time = f"{current_date_str[:10]}T00:00:00Z"
                            else:
                                date_with_year = current_date_str if str(now_utc.year) in current_date_str else f"{current_date_str} {now_utc.year}"
                                parsed_fallback = dateutil_parser.parse(date_with_year, default=now_utc)
                                iso_utc_time = parsed_fallback.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT00:00:00Z")
                        except Exception:
                            iso_utc_time = f"{current_date_str[:10]}T00:00:00Z" if re.match(r"^\d{4}-\d{2}-\d{2}", current_date_str) else now_utc.strftime("%Y-%m-%dT00:00:00Z")
                    else:
                        continue

                all_events.append(CalendarEvent(
                    time=iso_utc_time,
                    currency=currency,
                    impact=impact,
                    event_name=event_name,
                    actual=actual if actual else None,
                    forecast=forecast if forecast else None,
                    previous=previous if previous else None
                ))
        
        logger.info(f"ForexFactory: Fetched {len(all_events)} events total.")
        return all_events


def fetch_forexfactory_feed_direct(max_cache_age: int = 3600, ignore_cache: bool = False) -> List[CalendarEvent]:
    """
    Lightweight zero-browser helper to fetch and parse FairEconomy JSON calendar feed.
    Safe for sub-minute background loops without Chromium overhead or port allocation.
    """
    feed_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    cache_path = Path(os.getcwd()) / "data" / "cache" / "ff_calendar_thisweek.json"
    raw_items = None

    if not ignore_cache and cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            age = time.time() - mtime
            if age <= max_cache_age:
                with open(cache_path, "r", encoding="utf-8") as f:
                    raw_items = json.load(f)
        except Exception:
            raw_items = None

    if not raw_items:
        try:
            req = urllib.request.Request(
                feed_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    raw_items = json.loads(resp.read().decode("utf-8"))
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(raw_items, f)
        except Exception as e:
            logger.debug(f"Direct FairEconomy HTTP fetch failed: {e}")

    if not raw_items and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw_items = json.load(f)
        except Exception:
            raw_items = None

    if not raw_items:
        return []

    eastern_tz = ZoneInfo("America/New_York")
    events = []
    for item in raw_items:
        raw_date = item.get("date", "")
        try:
            parsed_dt = dateutil_parser.isoparse(raw_date) if hasattr(dateutil_parser, "isoparse") else dateutil_parser.parse(raw_date)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=eastern_tz)
            iso_time = parsed_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            iso_time = raw_date

        raw_impact = item.get("impact", "Low").strip().capitalize()
        impact = raw_impact if raw_impact in ["High", "Medium", "Low"] else "Low"

        currency = item.get("country", "").strip().upper()
        title = item.get("title", "").strip()
        raw_actual = item.get("actual")
        actual = str(raw_actual).strip() if raw_actual is not None and str(raw_actual).strip() != "" else None
        forecast = item.get("forecast") or None
        previous = item.get("previous") or None

        events.append(CalendarEvent(
            time=iso_time,
            currency=currency,
            impact=impact,
            event_name=title,
            actual=actual,
            forecast=forecast if forecast else None,
            previous=previous if previous else None,
            country=currency[:2] if currency else None
        ))

    return events
