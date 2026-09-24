# ==============================================================================
# File: scrapers/calendar/calendar_investing.py
# ==============================================================================

import logging
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Any, Optional

from scrapers.base_scraper import BaseScraper
from scrapers.models import CalendarEvent

logger = logging.getLogger("TradingAgent.InvestingScraper")

class InvestingCalendarScraper(BaseScraper):
    def __init__(self, headless=True, profile_name="investing_calendar"):
        super().__init__(headless, profile_name, load_mode="eager", no_imgs=True)
        self.target_url = "https://www.investing.com/economic-calendar/"

    def _apply_time_filter_human_like(self, time_filter: str) -> bool:
        if not self.page:
            return False
        page_obj: Any = self.page
        now = datetime.now()
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
                btn = page_obj.ele(sel, timeout=1)
                if btn and btn.states.is_displayed:
                    btn.click(by_js=True)
                    page_obj.wait(2.0)
                    return True
            except Exception:
                pass

        try:
            custom_btn = page_obj.ele('tag:button@@text():Custom dates', timeout=1)
            if not custom_btn or not custom_btn.states.is_displayed:
                custom_btn = page_obj.ele("xpath://button[contains(normalize-space(), 'Custom')]", timeout=1)

            if not custom_btn or not custom_btn.states.is_displayed:
                # Jika tombol Custom dates tidak ditemukan, coba ekstrak data yang ada
                return False

            custom_btn.scroll.to_center()
            page_obj.wait(0.5)

            page_obj.listen.start('economic-calendar')
            custom_btn.click(by_js=True)
            page_obj.wait(0.5)

            picker_container = page_obj.ele("xpath://div[contains(@class, 'DateRangePicker') or contains(@class, 'date-range-picker') or @data-test='date-range-picker']", timeout=4)
            if not picker_container:
                custom_btn.click(by_js=True)
                page_obj.wait(1.0)
                picker_container = page_obj.ele("xpath://div[contains(@class, 'DateRangePicker') or contains(@class, 'date-range-picker') or @data-test='date-range-picker']", timeout=3)

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
                start_cell = page_obj.ele(f'xpath://div[@data-date="{start_str}"]', timeout=3)
                if start_cell:
                    start_cell.click(by_js=True)
                    page_obj.wait(0.3)

                end_cell = page_obj.ele(f'xpath://div[@data-date="{end_str}"]', timeout=3)
                if end_cell:
                    end_cell.click(by_js=True)
                    page_obj.wait(0.3)

            apply_btn = page_obj.ele('xpath://button[contains(normalize-space(), "Apply") or @data-test="date-picker-apply"]', timeout=3)
            if apply_btn:
                apply_btn.click(by_js=True)
            else:
                page_obj.listen.stop()
                return False

            packet = page_obj.listen.wait(timeout=6.0)
            if packet:
                page_obj.wait(1.5)
            else:
                page_obj.wait(2.5)

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
            if getattr(self, 'is_closed', False):
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
                    'xpath://button[contains(., "Load more") or contains(., "Load More") '
                    'or contains(., "Show more")]',
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
                    refreshed_count = page_obj.run_js(
                        'return arguments[0] ? arguments[0].querySelectorAll("tr").length : 0', table
                    ) or 0
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

    def fetch_events(self, fast_mode: bool = False, time_filter: Optional[str] = None) -> List[CalendarEvent]:
        if not self.page:
            return []
        page_obj: Any = self.page
        page_obj.set.window.size(1920, 1080)
        wait_selector = 'xpath://button[contains(., "This Week") or contains(., "Today") or contains(., "This week")] | //table | //div[@id="economicCalendarData"]'
        
        all_events_dict = {}
        
        logger.info(f"Navigating to {self.target_url}")
        success = self.navigate_with_fallback(self.target_url, wait_selector, timeout=25)
        if not success or getattr(self, 'is_closed', False):
            if not success:
                logger.error(f"Failed to load {self.target_url}")
            return []
            
        try:
            pop_up_close = page_obj.ele('css:[data-test="sign-up-dialog-close-button"]', timeout=1.5)
            if pop_up_close and pop_up_close.states.is_displayed:
                pop_up_close.click(by_js=True)
                page_obj.wait(0.5)
        except Exception:
            pass

        if fast_mode:
            # Active Polling Mode
            table_ele = self._find_calendar_table()
            if not table_ele:
                logger.warning("Could not find table element in fast_mode")
                return []
                
            table_html = table_ele.inner_html
            soup = BeautifulSoup(table_html, "html.parser")
            return self._parse_table_html(soup, all_events_dict)

        # Normal Mode: jika time_filter diberikan gunakan filter tersebut, jika tidak gunakan default This Week & Next Week
        time_filters = [time_filter] if time_filter else ["This Week", "Next Week"]
        
        for time_filter in time_filters:
            if getattr(self, 'is_closed', False):
                break
            filter_success = self._apply_time_filter_human_like(time_filter)
            if not filter_success:
                logger.warning(f"Failed to apply time filter: {time_filter}")

            self._load_all_calendar_rows()

            table_ele = self._find_calendar_table()
            if not table_ele:
                logger.warning(f"Could not find table element after applying filter {time_filter}")
                continue
                
            table_html = table_ele.inner_html
            soup = BeautifulSoup(table_html, "html.parser")
            self._parse_table_html(soup, all_events_dict)

        return list(all_events_dict.values())

    def _parse_table_html(self, soup: BeautifulSoup, all_events_dict: dict) -> List[CalendarEvent]:
        _MONTH_RE = re.compile(r"\s*\((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q\d|H\d)\)", re.IGNORECASE)
        from datetime import datetime, timezone
        current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Deteksi timezone browser atau system lokal
        src_tz = datetime.now().astimezone().tzinfo
        if hasattr(self, 'page') and self.page:
            try:
                page_obj: Any = self.page
                browser_tz_str = page_obj.run_js('return Intl.DateTimeFormat().resolvedOptions().timeZone')
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
            
            cc_map = {"US": "USD", "EU": "EUR", "EZ": "EUR", "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR", 
                      "GB": "GBP", "UK": "GBP", "JP": "JPY", "AUD": "AUD", "CA": "CAD", "CH": "CHF", "NZ": "NZD", "CN": "CNY"}
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
