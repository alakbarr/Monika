#!/usr/bin/env python3
"""
Update Economic Calendar Data for Monika Trading Agent.
Fetches high/medium/low impact macro economic events for the current week and next week,
and persists them to PostgreSQL database, refreshing last_calendar_fetch_at.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Add trading-agent to sys.path
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_script_dir)
_ta_dir = os.path.join(_root_dir, "trading-agent")

if _ta_dir not in sys.path:
    sys.path.insert(0, _ta_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("UpdateEconomicCalendar")


async def update_calendar(headless: bool = True) -> dict:
    from database.db import init_db, get_session, close_db
    from database.adapters import batch_save_calendar
    from database.models import EconomicCalendar, SystemConfig
    from sqlalchemy import select, func

    logger.info("Initializing database connection...")
    await init_db()

    events = []
    source = "investing"

    # 1. Fetch from Investing.com (primary source: covers this week and next week)
    logger.info("Fetching economic calendar events from Investing.com (This Week & Next Week)...")
    try:
        from scrapers.calendar.calendar_investing import InvestingCalendarScraper
        scraper = InvestingCalendarScraper(headless=headless)
        try:
            loop = asyncio.get_running_loop()
            events = await loop.run_in_executor(None, lambda: scraper.fetch_events(fast_mode=False))
            if events:
                logger.info(f"Retrieved {len(events)} events from Investing.com")
        finally:
            scraper.close()
    except Exception as e:
        logger.warning(f"Investing.com fetch failed: {e}")
        events = []

    # 2. Fallback to ForexFactory if Investing failed
    if not events:
        logger.info("Falling back to ForexFactory scraper...")
        source = "forexfactory"
        try:
            from scrapers.calendar.calendar_forexfactory import ForexFactoryCalendarScraper
            ff = ForexFactoryCalendarScraper(headless=headless)
            try:
                events = ff.fetch_feed_events(ignore_cache=True)
                if events:
                    logger.info(f"Retrieved {len(events)} events from ForexFactory feed")
            finally:
                ff.close()
        except Exception as e:
            logger.warning(f"ForexFactory fallback failed: {e}")
            events = []

    # 3. Fallback to Finnhub if both failed
    if not events:
        logger.info("Falling back to Finnhub calendar scraper...")
        source = "finnhub"
        try:
            from scrapers.calendar.calendar_finnhub import FinnhubCalendarScraper
            fh = FinnhubCalendarScraper()
            if hasattr(fh, "afetch_today_events"):
                events = await fh.afetch_today_events()
            else:
                events = fh.fetch_today_events()
            if events:
                logger.info(f"Retrieved {len(events)} events from Finnhub")
        except Exception as e:
            logger.warning(f"Finnhub fallback failed: {e}")
            events = []

    if not events:
        logger.error("All economic calendar scraper sources failed to return events.")
        await close_db()
        return {"saved": 0, "status": "failed", "source": source}

    # Save events to database
    logger.info(f"Persisting {len(events)} events to database...")
    async with get_session() as session:
        saved_count = await batch_save_calendar(session, events)

    # Verify and inspect updated state
    async with get_session() as session:
        now_utc = datetime.now(timezone.utc)
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "last_calendar_fetch_at")
        )).scalar_one_or_none()
        total_in_db = (await session.execute(
            select(func.count(EconomicCalendar.id))
        )).scalar_one()
        upcoming_count = (await session.execute(
            select(func.count(EconomicCalendar.id)).where(EconomicCalendar.event_time >= now_utc)
        )).scalar_one()
        max_time = (await session.execute(
            select(func.max(EconomicCalendar.event_time))
        )).scalar_one_or_none()
        min_time = (await session.execute(
            select(func.min(EconomicCalendar.event_time))
        )).scalar_one_or_none()

    await close_db()

    logger.info("=" * 60)
    logger.info("  ECONOMIC CALENDAR UPDATE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Source:               {source}")
    logger.info(f"  Scraped Events:       {len(events)}")
    logger.info(f"  Saved New Events:     {saved_count}")
    logger.info(f"  Total Events in DB:   {total_in_db}")
    logger.info(f"  Upcoming Events:      {upcoming_count}")
    logger.info(f"  Time Span in DB:      {min_time} -> {max_time}")
    logger.info(f"  Last Fetch Recorded:  {cfg.value if cfg else 'N/A'}")
    logger.info("=" * 60)

    return {
        "saved": saved_count,
        "scraped": len(events),
        "total_db": total_in_db,
        "upcoming": upcoming_count,
        "source": source,
        "max_time": str(max_time),
        "status": "success",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update economic calendar data in database")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible mode (default: headless)")
    args = parser.parse_args()

    res = asyncio.run(update_calendar(headless=not args.headed))
    if res.get("status") == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
