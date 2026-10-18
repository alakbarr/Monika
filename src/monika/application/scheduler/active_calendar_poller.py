# ==============================================================================
# File: scheduler/active_calendar_poller.py
# ==============================================================================

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select

import monika.core.primitives.clock as clock
from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_investing import InvestingCalendarScraper
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import EconomicCalendar, NewsItem

logger = logging.getLogger("TradingAgent.CalendarPoller")


class ActiveCalendarPoller:
    def __init__(self, settings: dict):
        self.settings = settings
        self.running = False
        self.poll_interval = 15  # seconds
        self.active_polling_tasks = set()
        self._background_tasks: set[asyncio.Task] = set()
        self._news_watcher: Optional[Any] = None
        self._post_release_analyzer: Optional[Any] = None

    async def start(self):
        self.running = True
        logger.info("ActiveCalendarPoller started. Monitoring schedule every 30s.")
        while self.running:
            try:
                await self._check_schedule()
            except Exception as e:
                logger.error(f"Error checking schedule: {e}")

            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

    def stop(self):
        self.running = False
        logger.info("ActiveCalendarPoller stopped.")

    async def _check_schedule(self):
        now = datetime.now(timezone.utc)
        # Standby 15 seconds before scheduled event_time to eliminate latency
        target_time = now + timedelta(seconds=15)
        # Don't poll for events older than 10 minutes (safety boundary)
        max_time = now - timedelta(minutes=10)

        async with get_session() as session:
            pending_events = (
                (
                    await session.execute(
                        select(EconomicCalendar)
                        .where(func.lower(EconomicCalendar.impact) == "high")
                        .where(EconomicCalendar.event_time <= target_time)
                        .where(EconomicCalendar.event_time >= max_time)
                        .where(EconomicCalendar.actual.is_(None))
                    )
                )
                .scalars()
                .all()
            )

            if pending_events:
                # Filter non-data events (speeches, meetings, etc.)
                valid_events = []
                skip_keywords = [
                    "speech",
                    "speak",
                    "speaks",
                    "meet",
                    "meeting",
                    "report",
                    "press conference",
                    "testimony",
                    "member",
                    "auction",
                ]
                for e in pending_events:
                    name_lower = e.event_name.lower()
                    if any(k in name_lower for k in skip_keywords):
                        continue
                    if not e.forecast and not e.previous:
                        continue
                    valid_events.append(e)

                # Group by exact time to bundle multiple concurrent releases
                times = set([e.event_time for e in valid_events if e.event_time])
                for t in times:
                    if t not in self.active_polling_tasks:
                        self.active_polling_tasks.add(t)
                        task = asyncio.create_task(self._poll_for_events(t))
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)

    async def _poll_for_events(self, event_time: datetime):
        logger.warning(f"Starting active polling for high-impact events scheduled at {event_time}")
        try:
            now = datetime.now(timezone.utc)
            # If event is in near future (pre-fetch standby), sleep until event time
            if event_time > now:
                delay = (event_time - now).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)

            # Aggressive polling window: 4 minutes from event release time
            end_time = datetime.now(timezone.utc) + timedelta(minutes=4)

            async with get_session() as session:
                db_events = (
                    (
                        await session.execute(
                            select(EconomicCalendar)
                            .where(EconomicCalendar.event_time == event_time)
                            .where(EconomicCalendar.impact == "high")
                        )
                    )
                    .scalars()
                    .all()
                )
                event_targets = [(e.id, e.event_name) for e in db_events if e.actual is None]

            if not event_targets:
                return

            target_names = [name for _, name in event_targets]
            captured_data = []

            scraper = InvestingCalendarScraper(headless=True)
            try:
                from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_forexfactory import (
                    fetch_forexfactory_feed_direct,
                )

                while datetime.now(timezone.utc) < end_time and self.running:
                    # 1. Tier 1: Fast direct HTTP feed (<300ms, zero browser overhead)
                    try:
                        fresh_ff = await asyncio.to_thread(
                            fetch_forexfactory_feed_direct, max_cache_age=10, ignore_cache=True
                        )
                        if fresh_ff:
                            matched_ff = []
                            for event_id, name in list(event_targets):
                                if name in target_names:
                                    for fresh in fresh_ff:
                                        if (
                                            fresh.event_name == name
                                            or name.lower() in fresh.event_name.lower()
                                            or fresh.event_name.lower() in name.lower()
                                        ) and fresh.actual:
                                            matched_ff.append(
                                                (event_id, name, fresh.actual, fresh.forecast, fresh.previous)
                                            )
                                            target_names.remove(name)
                                            break

                            if matched_ff:
                                async with get_session() as session:
                                    for event_id, name, act, fc, prev in matched_ff:
                                        ev = (
                                            await session.execute(
                                                select(EconomicCalendar).where(EconomicCalendar.id == event_id)
                                            )
                                        ).scalar_one_or_none()
                                        if ev:
                                            ev.actual = act
                                            ev.forecast = fc
                                            ev.previous = prev
                                            captured_data.append(
                                                {
                                                    "event_name": ev.event_name,
                                                    "actual": act,
                                                    "forecast": fc,
                                                    "previous": prev,
                                                    "currency": ev.currency,
                                                    "impact": ev.impact,
                                                }
                                            )
                                    await session.commit()

                            if not target_names:
                                break
                    except Exception as ff_err:
                        logger.debug(f"Direct feed check error: {ff_err}")

                    # 2. Tier 2: Fallback to Chromium Investing scraper only if direct feed didn't resolve targets
                    if target_names and datetime.now(timezone.utc) < end_time and self.running:
                        try:
                            fresh_data = await asyncio.to_thread(scraper.fetch_events, True)
                            if fresh_data:
                                matched_inv = []
                                for event_id, name in list(event_targets):
                                    if name in target_names:
                                        for fresh in fresh_data:
                                            if fresh.event_name == name and fresh.actual:
                                                matched_inv.append(
                                                    (event_id, name, fresh.actual, fresh.forecast, fresh.previous)
                                                )
                                                target_names.remove(name)
                                                break
                                if matched_inv:
                                    async with get_session() as session:
                                        for event_id, name, act, fc, prev in matched_inv:
                                            ev = (
                                                await session.execute(
                                                    select(EconomicCalendar).where(EconomicCalendar.id == event_id)
                                                )
                                            ).scalar_one_or_none()
                                            if ev:
                                                ev.actual = act
                                                ev.forecast = fc
                                                ev.previous = prev
                                                captured_data.append(
                                                    {
                                                        "event_name": ev.event_name,
                                                        "actual": act,
                                                        "forecast": fc,
                                                        "previous": prev,
                                                        "currency": ev.currency,
                                                        "impact": ev.impact,
                                                    }
                                                )
                                        await session.commit()
                                if not target_names:
                                    break
                        except Exception as inv_err:
                            logger.debug(f"Investing fallback check error: {inv_err}")

                    await asyncio.sleep(self.poll_interval)
            finally:
                if scraper:
                    try:
                        scraper.close()
                    except Exception:
                        pass

            # After loop ends (either by finding all, or timing out)
            if captured_data:
                async with get_session() as session:
                    await self._generate_pseudo_news(session, captured_data)
            elif target_names:
                logger.info(f"Active polling timed out. Missing data for: {target_names}")
        finally:
            self.active_polling_tasks.discard(event_time)

    async def _generate_pseudo_news(self, session, events):
        titles = []
        for e in events:
            ev_name = e.get("event_name") if isinstance(e, dict) else getattr(e, "event_name", "")
            act = e.get("actual") if isinstance(e, dict) else getattr(e, "actual", "")
            fc = e.get("forecast") if isinstance(e, dict) else getattr(e, "forecast", "")
            prev = e.get("previous") if isinstance(e, dict) else getattr(e, "previous", "")
            txt = f"{ev_name} actual: {act}"
            if fc:
                txt += f" vs {fc} forecast"
            if prev:
                txt += f" (prev: {prev})"
            titles.append(txt)

        combined_title = "BREAKING DATA: " + " | ".join(titles)
        tags_set = set([e.get("currency") if isinstance(e, dict) else getattr(e, "currency", None) for e in events])
        tags_set = {t for t in tags_set if t}
        tags = ",".join(tags_set) if tags_set else None

        now_dt = clock.now()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)

        has_post_release_analyzer = getattr(self, "_post_release_analyzer", None) is not None
        impact_level = "HIGH" if has_post_release_analyzer else "BREAKING"

        news = NewsItem(
            source="calendar_poller",
            title=combined_title,
            summary="Instant release capture by Active Calendar Poller.",
            url=f"internal://calendar_poller/{now_dt.timestamp()}",
            published_at=now_dt,
            currency_tags=tags,
            fetched_at=now_dt,
            impact=impact_level,
            sentiment=None,
        )
        session.add(news)
        await session.commit()
        logger.info(f"[ActiveCalendarPoller] Recorded release data: {combined_title} (impact={impact_level})")

        # Only trigger NewsWatcher directly if PostReleaseAnalyzer is not present to handle it
        if not has_post_release_analyzer and self._news_watcher is not None:
            try:
                logger.info("[ActiveCalendarPoller] Triggering immediate NewsWatcher run for pseudo-news")
                nw_task = asyncio.create_task(self._news_watcher.run_once())
                self._background_tasks.add(nw_task)
                nw_task.add_done_callback(self._background_tasks.discard)
            except Exception as e:
                logger.debug(f"Direct NewsWatcher trigger failed (non-fatal): {e}")

        # Hook MacroTriggerRouter to immediately ingest granular decomposition / statements
        for e in events:
            ev_name = e.get("event_name") if isinstance(e, dict) else getattr(e, "event_name", "")
            if ev_name:

                async def _run_macro_trigger(name: str):
                    try:
                        from monika.infrastructure.data_ingestion.scrapers.macro.macro_trigger_router import (
                            MacroTriggerRouter,
                        )

                        async with get_session() as bg_session:
                            router = MacroTriggerRouter(bg_session)
                            await router.on_calendar_event_released(name)
                    except Exception as bg_err:
                        logger.debug(
                            f"[ActiveCalendarPoller] Background MacroTriggerRouter error for '{name}': {bg_err}"
                        )

                logger.info(f"[ActiveCalendarPoller] Routing calendar release '{ev_name}' to MacroTriggerRouter...")
                r_task = asyncio.create_task(_run_macro_trigger(ev_name))
                self._background_tasks.add(r_task)
                r_task.add_done_callback(self._background_tasks.discard)
