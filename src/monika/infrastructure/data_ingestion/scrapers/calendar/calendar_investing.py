# ==============================================================================
# File: scrapers/calendar/calendar_investing.py
# ==============================================================================

import json
import logging
import os
import re
import shutil
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from monika.infrastructure.data_ingestion.scrapers.base_scraper import (
    BaseScraper,
    ProfileLock,
    _PROFILE_LOCKS,
    _PROFILE_LOCKS_GUARD,
    PROFILE_LOCK_TIMEOUT_SECONDS,
)
from monika.infrastructure.data_ingestion.scrapers.models import CalendarEvent

logger = logging.getLogger("TradingAgent.InvestingScraper")


class InvestingCalendarScraper(BaseScraper):
    CACHE_TTL_SECONDS: float = 900.0  # 15 minutes TTL
    CACHE_FILE: Path = Path(os.getcwd()) / "data" / "cache" / "investing_calendar.json"
    _SHARED_CACHE: Dict[Tuple[bool, str], Tuple[float, List[CalendarEvent]]] = {}
    _CACHE_LOCK = threading.Lock()

    def __init__(
        self,
        headless: bool = True,
        profile_name: Optional[str] = "investing_calendar",
        lazy_browser: bool = False,
    ):
        self.lazy_browser = lazy_browser
        self.target_url = "https://www.investing.com/economic-calendar/"
        # Retain instance cache attribute for backwards compatibility
        self._cache = self._SHARED_CACHE

        if not lazy_browser:
            if profile_name:
                self.cleanup_profile_cache_bloat(profile_name)
            super().__init__(headless, profile_name, load_mode="eager", no_imgs=True)
        else:
            self.headless = headless
            self.profile_name = profile_name
            self.load_mode = "eager"
            self.no_imgs = True
            self._temp_profile_dir = None
            self.is_closed = False
            self.browser_pid: Optional[int] = None
            self._browser_pid: Optional[int] = None
            self._close_lock = threading.Lock()
            self._profile_lock: Optional[ProfileLock] = None
            self._acquired_profile_lock: bool = False
            self.page: Any = None

    @classmethod
    def cleanup_profile_cache_bloat(cls, profile_name: Optional[str] = "investing_calendar") -> int:
        """
        Membersihkan cache HTTP dan GPU browser sementara jika ukurannya melebihi 100MB,
        mencegah pembengkakan direktori profil yang memperlambat startup Chromium.
        """
        if not profile_name:
            return 0
        base_dir = Path(os.getcwd())
        profile_dir = base_dir / "data" / "sessions" / "browser_profile" / profile_name
        if not profile_dir.exists():
            return 0

        disposable_subdirs = [
            profile_dir / "Default" / "Cache",
            profile_dir / "Default" / "Code Cache",
            profile_dir / "Default" / "GPUCache",
            profile_dir / "Default" / "Service Worker" / "CacheStorage",
            profile_dir / "GrShaderCache",
            profile_dir / "ShaderCache",
        ]

        total_size = 0
        for d in disposable_subdirs:
            if d.exists():
                for f in d.rglob("*"):
                    if f.is_file():
                        try:
                            total_size += f.stat().st_size
                        except Exception:
                            pass

        cleaned_bytes = 0
        if total_size > 100 * 1024 * 1024:
            for d in disposable_subdirs:
                if d.exists():
                    try:
                        shutil.rmtree(d, ignore_errors=True)
                        cleaned_bytes += total_size
                    except Exception:
                        pass
            logger.info(
                f"[InvestingCalendarScraper] Pruned {total_size / (1024 * 1024):.1f}MB of disposable browser cache from profile '{profile_name}'."
            )
        return cleaned_bytes

    def ensure_browser(self) -> Any:
        """Inisialisasi proses browser Chromium sesuai kebutuhan saat lazy_browser=True."""
        if getattr(self, "page", None) is not None or getattr(self, "is_closed", False):
            return self.page

        if self.profile_name:
            with _PROFILE_LOCKS_GUARD:
                if self.profile_name not in _PROFILE_LOCKS:
                    _PROFILE_LOCKS[self.profile_name] = ProfileLock(self.profile_name)
                self._profile_lock = _PROFILE_LOCKS[self.profile_name]

            acquired = self._profile_lock.acquire(timeout=PROFILE_LOCK_TIMEOUT_SECONDS)
            if acquired:
                self._acquired_profile_lock = True
            else:
                logger.warning(
                    f"[InvestingCalendarScraper] Profile lock '{self.profile_name}' could not be acquired "
                    f"within {PROFILE_LOCK_TIMEOUT_SECONDS}s. Automatically falling back to an "
                    f"isolated ephemeral browser profile."
                )
                self._profile_lock = None
                self._acquired_profile_lock = False
                self.profile_name = None

        if self.profile_name:
            self.cleanup_profile_cache_bloat(self.profile_name)

        try:
            self.page = self._initialize_browser(self.headless)
        except Exception:
            self.close()
            raise
        return self.page

    @classmethod
    def clear_cache(cls) -> None:
        """Membersihkan seluruh cache kalender (in-memory dan disk)."""
        with cls._CACHE_LOCK:
            cls._SHARED_CACHE.clear()
            if cls.CACHE_FILE.exists():
                try:
                    cls.CACHE_FILE.unlink(missing_ok=True)
                except Exception:
                    pass

    @classmethod
    def get_cached_events(
        cls, fast_mode: bool = False, time_filter: Optional[str] = None
    ) -> Optional[List[CalendarEvent]]:
        """
        Mengambil data event kalender dari cache (memory atau disk) tanpa membuka Chromium.
        Mengembalikan None jika cache belum tersedia, kosong, atau kedaluwarsa (>15 menit).
        """
        cache_key = (fast_mode, str(time_filter).lower() if time_filter else "default")
        now_ts = time.time()

        with cls._CACHE_LOCK:
            # 1. Periksa in-memory cache
            if cache_key in cls._SHARED_CACHE:
                cache_time, cached_events = cls._SHARED_CACHE[cache_key]
                if now_ts - cache_time < cls.CACHE_TTL_SECONDS and cached_events:
                    return list(cached_events)

            # 2. Periksa disk cache
            if cls.CACHE_FILE.exists():
                try:
                    mtime = cls.CACHE_FILE.stat().st_mtime
                    if now_ts - mtime < cls.CACHE_TTL_SECONDS:
                        with open(cls.CACHE_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        key_str = f"{fast_mode}_{str(time_filter).lower() if time_filter else 'default'}"
                        if key_str in data:
                            raw_list = data[key_str]
                            events = [CalendarEvent(**item) for item in raw_list]
                            if events:
                                cls._SHARED_CACHE[cache_key] = (mtime, events)
                                return list(events)
                except Exception as e:
                    logger.debug(f"[InvestingCalendarScraper] Disk cache read note: {e}")

        return None

    @classmethod
    def save_cached_events(cls, fast_mode: bool, time_filter: Optional[str], events: List[CalendarEvent]) -> None:
        """Menyimpan data event kalender ke cache memori bersama dan file disk secara atomik."""
        if not events:
            return
        cache_key = (fast_mode, str(time_filter).lower() if time_filter else "default")
        key_str = f"{fast_mode}_{str(time_filter).lower() if time_filter else 'default'}"
        now_ts = time.time()

        with cls._CACHE_LOCK:
            cls._SHARED_CACHE[cache_key] = (now_ts, list(events))
            try:
                cls.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                existing = {}
                if cls.CACHE_FILE.exists():
                    try:
                        with open(cls.CACHE_FILE, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                    except Exception:
                        existing = {}
                existing[key_str] = [asdict(e) for e in events]
                tmp_path = cls.CACHE_FILE.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f)
                tmp_path.replace(cls.CACHE_FILE)
            except Exception as e:
                logger.debug(f"[InvestingCalendarScraper] Disk cache write note: {e}")

    def _apply_time_filter_human_like(self, time_filter: str) -> bool:
        if not self.page:
            return False
        page_obj: Any = self.page
        now = datetime.now(timezone.utc)
        if time_filter.lower() == "today":
            start_date = now
            end_date = now
        elif time_filter.lower() == "this week":
            start_date = now - timedelta(days=now.weekday())
            end_date = start_date + timedelta(days=6)
        elif time_filter.lower() == "next week":
            start_date = now + timedelta(days=7 - now.weekday())
            end_date = start_date + timedelta(days=6)
        else:
            start_date = now
            end_date = now

        start_str = start_date.strftime("%m/%d/%Y")
        end_str = end_date.strftime("%m/%d/%Y")

        # Coba klik tab button langsung (Today, This Week, Next Week, Yesterday, Tomorrow)
        tab_map = {
            "today": [
                "xpath://button[normalize-space(.)='Today' or contains(normalize-space(), 'Today')]",
                "tag:button@@text():Today",
                "#timeFrame_today",
            ],
            "this week": [
                "xpath://button[normalize-space(.)='This Week' or contains(normalize-space(), 'This Week')]",
                "tag:button@@text():This Week",
                "#timeFrame_thisWeek",
            ],
            "next week": [
                "xpath://button[normalize-space(.)='Next Week' or contains(normalize-space(), 'Next Week')]",
                "tag:button@@text():Next Week",
                "#timeFrame_nextWeek",
            ],
            "yesterday": [
                "xpath://button[normalize-space(.)='Yesterday' or contains(normalize-space(), 'Yesterday')]",
                "tag:button@@text():Yesterday",
                "#timeFrame_yesterday",
            ],
            "tomorrow": [
                "xpath://button[normalize-space(.)='Tomorrow' or contains(normalize-space(), 'Tomorrow')]",
                "tag:button@@text():Tomorrow",
                "#timeFrame_tomorrow",
            ],
        }
        for sel in tab_map.get(time_filter.lower(), []):
            try:
                btn = page_obj.ele(sel, timeout=0.8)
                if btn:
                    try:
                        btn.click(by_js=True)
                    except Exception:
                        page_obj.run_js("arguments[0].click()", btn)
                    page_obj.wait(1.5)
                    return True
            except Exception:
                pass

        try:
            custom_btn = page_obj.ele("tag:button@@text():Custom dates", timeout=0.8)
            if not custom_btn:
                custom_btn = page_obj.ele("xpath://button[contains(normalize-space(), 'Custom')]", timeout=0.8)

            if not custom_btn:
                # Jika tombol Custom dates tidak ditemukan, coba ekstrak data yang ada
                return False

            try:
                custom_btn.scroll.to_center()
            except Exception:
                pass
            page_obj.wait(0.3)

            page_obj.listen.start("economic-calendar")
            try:
                custom_btn.click(by_js=True)
            except Exception:
                page_obj.run_js("arguments[0].click()", custom_btn)
            page_obj.wait(0.4)

            picker_container = page_obj.ele(
                "xpath://div[contains(@class, 'DateRangePicker') or contains(@class, 'date-range-picker') or @data-test='date-range-picker']",
                timeout=2.0,
            )
            if not picker_container:
                try:
                    custom_btn.click(by_js=True)
                except Exception:
                    page_obj.run_js("arguments[0].click()", custom_btn)
                page_obj.wait(0.5)
                picker_container = page_obj.ele(
                    "xpath://div[contains(@class, 'DateRangePicker') or contains(@class, 'date-range-picker') or @data-test='date-range-picker']",
                    timeout=1.5,
                )

            if not picker_container:
                page_obj.listen.stop()
                return False

            # Coba input teks MM/DD/YYYY jika tersedia
            date_inputs = picker_container.eles("tag:input")
            if len(date_inputs) >= 2:
                try:
                    date_inputs[0].clear()
                    date_inputs[0].input(start_str)
                    date_inputs[1].clear()
                    date_inputs[1].input(end_str)
                except Exception:
                    pass
            else:
                start_cell = page_obj.ele(f'xpath://div[@data-date="{start_str}"]', timeout=1.5)
                if start_cell:
                    try:
                        start_cell.click(by_js=True)
                    except Exception:
                        page_obj.run_js("arguments[0].click()", start_cell)
                    page_obj.wait(0.2)

                end_cell = page_obj.ele(f'xpath://div[@data-date="{end_str}"]', timeout=1.5)
                if end_cell:
                    try:
                        end_cell.click(by_js=True)
                    except Exception:
                        page_obj.run_js("arguments[0].click()", end_cell)
                    page_obj.wait(0.2)

            apply_btn = page_obj.ele(
                'xpath://button[contains(normalize-space(), "Apply") or @data-test="date-picker-apply"]', timeout=1.5
            )
            if apply_btn:
                try:
                    apply_btn.click(by_js=True)
                except Exception:
                    page_obj.run_js("arguments[0].click()", apply_btn)
            else:
                page_obj.listen.stop()
                return False

            packet = page_obj.listen.wait(timeout=3.0)
            if packet:
                page_obj.wait(1.0)
            else:
                page_obj.wait(1.5)

            page_obj.listen.stop()
            return True
        except Exception as e:
            logger.error(f"Error in time filter {time_filter}: {e}")
            try:
                page_obj.listen.stop()
            except Exception:
                pass
            return False

    def _find_calendar_table(self):
        """Mencari elemen table kalender ekonomi utama di DOM dengan multi-selector fallback."""
        if not self.page:
            return None
        page_obj: Any = self.page
        modern_selectors = [
            'xpath://table[contains(@class, "datatable") or @id="economicCalendarData" or contains(@class, "genTbl")]',
            "css:[data-test='calendar-table']",
            "css:.economic-calendar",
        ]
        for sel in modern_selectors:
            ele = page_obj.ele(sel, timeout=0.5)
            if ele:
                return ele

        for t in page_obj.eles("tag:table"):
            try:
                text = t.text.lower()
                if "event" in text and ("imp" in text or "cur" in text or "forecast" in text):
                    return t
                if len(t.eles("tag:tr")) > 10:
                    return t
            except Exception:
                pass
        return page_obj.ele("css:table", timeout=1)

    def _load_all_calendar_rows(self) -> None:
        if not self.page:
            return
        page_obj: Any = self.page
        consecutive_stall_count = 0
        previous_row_count = 0
        MAX_SCROLL_ITERATIONS = 2

        for _ in range(MAX_SCROLL_ITERATIONS):
            if getattr(self, "is_closed", False):
                break
            try:
                table = self._find_calendar_table()
                if not table:
                    page_obj.scroll.to_bottom()
                    page_obj.wait(0.3)
                    continue

                page_obj.scroll.to_bottom()
                page_obj.wait(0.2)
            except Exception:
                pass

            try:
                load_more_button = page_obj.ele(
                    'xpath://button[contains(., "Load more") or contains(., "Load More") or contains(., "Show more")]',
                    timeout=0.3,
                )
                if load_more_button and load_more_button.states.is_displayed:
                    load_more_button.click(by_js=True)
                    page_obj.wait(0.5)
            except Exception:
                pass

            try:
                table = self._find_calendar_table()
                if table:
                    refreshed_count = (
                        page_obj.run_js('return arguments[0] ? arguments[0].querySelectorAll("tr").length : 0', table)
                        or 0
                    )
                else:
                    refreshed_count = 0
                if abs(refreshed_count - previous_row_count) <= 2:
                    consecutive_stall_count += 1
                    if consecutive_stall_count >= 1:
                        break
                else:
                    consecutive_stall_count = 0
                previous_row_count = refreshed_count
            except Exception:
                pass

    def fetch_events(
        self, fast_mode: bool = False, time_filter: Optional[str] = None, force_refresh: bool = False
    ) -> List[CalendarEvent]:
        # 1. Periksa in-memory dan disk cache terlebih dahulu untuk menghindari browser launch sia-sia
        if not force_refresh:
            cached_events = self.get_cached_events(fast_mode=fast_mode, time_filter=time_filter)
            if cached_events:
                logger.info(
                    f"Returning {len(cached_events)} Investing.com calendar events from cache "
                    f"(fast_mode={fast_mode}, filter={time_filter or 'default'})"
                )
                return cached_events

        # 2. Inisialisasi browser bila belum siap (mode lazy)
        if getattr(self, "lazy_browser", False):
            self.ensure_browser()

        if not self.page:
            return self._fallback_forexfactory()
        page_obj: Any = self.page
        page_obj.set.window.size(1920, 1080)
        wait_selector = 'xpath://button[contains(., "This Week") or contains(., "Today") or contains(., "This week")] | //table | //div[@id="economicCalendarData"]'

        all_events_dict = {}

        logger.info(f"Navigating to {self.target_url}")
        success = self.navigate_with_fallback(self.target_url, wait_selector, timeout=20)
        if not success or getattr(self, "is_closed", False):
            if not success:
                logger.warning(f"Failed to load {self.target_url}, falling back to ForexFactory backup feed.")
            return self._fallback_forexfactory()

        try:
            pop_up_close = page_obj.ele('css:[data-test="sign-up-dialog-close-button"]', timeout=1.0)
            if pop_up_close:
                try:
                    pop_up_close.click(by_js=True)
                except Exception:
                    page_obj.run_js("arguments[0].click()", pop_up_close)
                page_obj.wait(0.3)
        except Exception:
            pass

        if fast_mode:
            # Active Polling Mode (Directly extract table DOM without slow human scrolling)
            table_ele = self._find_calendar_table()
            if not table_ele:
                logger.warning("Could not find table element in fast_mode, falling back to ForexFactory backup feed.")
                return self._fallback_forexfactory()

            table_html = table_ele.inner_html
            soup = BeautifulSoup(table_html, "html.parser")
            events = self._parse_table_html(soup, all_events_dict)
            if events:
                self.save_cached_events(fast_mode=fast_mode, time_filter=time_filter, events=events)
                return events
            return self._fallback_forexfactory()

        # Normal Mode: jika time_filter diberikan gunakan filter tersebut, jika tidak gunakan default This Week & Next Week
        time_filters = [time_filter] if time_filter else ["This Week", "Next Week"]

        for filter_label in time_filters:
            if getattr(self, "is_closed", False):
                break
            filter_success = self._apply_time_filter_human_like(filter_label)
            if not filter_success:
                logger.warning(f"Failed to apply time filter: {filter_label}")

            self._load_all_calendar_rows()

            table_ele = self._find_calendar_table()
            if not table_ele:
                logger.warning(f"Could not find table element after applying filter {filter_label}")
                continue

            table_html = table_ele.inner_html
            soup = BeautifulSoup(table_html, "html.parser")
            self._parse_table_html(soup, all_events_dict)

        res = list(all_events_dict.values())
        if res:
            self.save_cached_events(fast_mode=fast_mode, time_filter=time_filter, events=res)
        return res

    def _fallback_forexfactory(self) -> List[CalendarEvent]:
        """Secondary seamless failover if Investing.com is unreachable or throttled."""
        try:
            from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_forexfactory import (
                fetch_forexfactory_feed_direct,
            )

            events = fetch_forexfactory_feed_direct()
            if events:
                logger.info(f"Failover successful: retrieved {len(events)} events from ForexFactory JSON backup feed.")
                return events
        except Exception as e:
            logger.error(f"Secondary ForexFactory calendar direct failover error: {e}")
        return []

    def _parse_table_html(self, soup: BeautifulSoup, all_events_dict: dict) -> List[CalendarEvent]:
        _MONTH_RE = re.compile(r"\s*\((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q\d|H\d)\)", re.IGNORECASE)
        from datetime import datetime, timezone

        current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Deteksi timezone browser atau system lokal
        src_tz = datetime.now(timezone.utc).astimezone().tzinfo
        if hasattr(self, "page") and self.page:
            try:
                page_obj: Any = self.page
                browser_tz_str = page_obj.run_js("return Intl.DateTimeFormat().resolvedOptions().timeZone")
                if browser_tz_str:
                    from zoneinfo import ZoneInfo

                    src_tz = ZoneInfo(browser_tz_str)
            except Exception:
                pass

        for row in soup.find_all("tr"):
            # Check for date header row (e.g. <td class="theDay"> or <th class="theDay">)
            day_cell = row.find("td", class_="theDay") or row.find("th", class_="theDay")
            if not day_cell and len(row.find_all("td")) == 1 and row.find("td", colspan=True):
                day_cell = row.find("td")

            if day_cell:
                raw_date_text = day_cell.get_text(strip=True)
                try:
                    from dateutil import parser as dateutil_parser

                    now_utc = datetime.now(timezone.utc)
                    parsed_dt = dateutil_parser.parse(raw_date_text, fuzzy=True, default=datetime(now_utc.year, 1, 1))
                    # Year boundary check: if current month is Dec and parsed month is Jan -> next year
                    if now_utc.month == 12 and parsed_dt.month == 1:
                        parsed_dt = parsed_dt.replace(year=now_utc.year + 1)
                    elif now_utc.month == 1 and parsed_dt.month == 12:
                        parsed_dt = parsed_dt.replace(year=now_utc.year - 1)
                    current_date_str = parsed_dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
                continue

            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            time_str = cells[1].get_text(strip=True)
            country_code = cells[2].get_text(strip=True).upper()

            cc_map = {
                "US": "USD",
                "EU": "EUR",
                "EZ": "EUR",
                "DE": "EUR",
                "FR": "EUR",
                "IT": "EUR",
                "ES": "EUR",
                "GB": "GBP",
                "UK": "GBP",
                "JP": "JPY",
                "AUD": "AUD",
                "CA": "CAD",
                "CH": "CHF",
                "NZ": "NZD",
                "CN": "CNY",
            }
            currency = cc_map.get(country_code, country_code)

            # if currency not in ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "CNY"]:
            #     continue

            raw_title = cells[3].get_text(separator=" ", strip=True)
            clean_title = re.split(r"Act:|Cons:|Prev\.:", raw_title)[0].strip()
            clean_title = _MONTH_RE.sub("", clean_title).strip()

            impact_html = str(cells[4]).lower()
            if "holiday" in impact_html or "holiday" in clean_title.lower():
                impact = "Low"
            else:
                muted_stars = impact_html.count("opacity-20")
                if muted_stars == 0:
                    impact = "High"
                elif muted_stars == 1:
                    impact = "Medium"
                else:
                    impact = "Low"

            actual = cells[5].get_text(strip=True)
            forecast = cells[6].get_text(strip=True)
            previous = cells[7].get_text(strip=True)

            if "Time" in time_str and "Cur" in currency:
                continue

            actual_val = actual if actual and actual not in ["", "-", "--"] else None
            forecast_val = forecast if forecast and forecast not in ["", "-", "--"] else None
            previous_val = previous if previous and previous not in ["", "-", "--"] else None

            if time_str and len(time_str) <= 5 and ":" in time_str:
                try:
                    naive_dt = datetime.strptime(f"{current_date_str} {time_str}", "%Y-%m-%d %H:%M")
                    local_dt = naive_dt.replace(tzinfo=src_tz)
                    full_time_str = local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    full_time_str = f"{current_date_str} {time_str}"
            else:
                full_time_str = f"{current_date_str} {time_str}" if time_str else current_date_str

            event_hash = f"{full_time_str}_{currency}_{clean_title}"
            all_events_dict[event_hash] = CalendarEvent(
                time=full_time_str,
                currency=currency,
                impact=impact,
                event_name=clean_title,
                actual=actual_val,
                forecast=forecast_val,
                previous=previous_val,
                country=country_code,
            )

        return list(all_events_dict.values())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = InvestingCalendarScraper(headless=True, profile_name="investing_calendar")
    events = scraper.fetch_events()

    print(f"\n--- Extracted {len(events)} events ---")
    for e in events:
        print(e)

    scraper.close()
