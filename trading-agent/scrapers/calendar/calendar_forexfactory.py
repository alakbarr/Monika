# ==============================================================================
# File: scrapers/calendar/calendar_forexfactory.py
# ==============================================================================
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from typing import List, Any

from scrapers.base_scraper import BaseScraper
from scrapers.models import CalendarEvent

logger = logging.getLogger("TradingAgent.ForexFactoryScraper")

class ForexFactoryCalendarScraper(BaseScraper):
    def __init__(self, headless=True, profile_name="ff_calendar"):
        super().__init__(headless, profile_name)
        self.urls = [
            "https://www.forexfactory.com/calendar?week=this",
            "https://www.forexfactory.com/calendar?week=next"
        ]

    def fetch_events(self) -> List[CalendarEvent]:
        all_events = []
        for url in self.urls:
            if getattr(self, 'is_closed', False):
                break
            logger.info(f"Navigating to ForexFactory: {url}")
            success = self.navigate_with_fallback(url, 'css:table.calendar__table', timeout=20)
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
