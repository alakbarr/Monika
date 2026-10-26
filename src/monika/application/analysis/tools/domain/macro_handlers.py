"""Macro domain tool handlers (FRED, COT, Yields, Calendar, Session)."""

import html as _html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock

logger = logging.getLogger("TradingAgent.MacroHandlers")


def _safe_isoformat(val: Any) -> Optional[str]:
    if val is None:
        return None
    iso_fn = getattr(val, "isoformat", None)
    if callable(iso_fn):
        return str(iso_fn())
    return str(val)


class MacroToolHandlers:
    """Handlers for macro-economic queries."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def get_market_session(
        self, session: Optional[AsyncSession] = None, dt: Optional[datetime] = None, **kwargs
    ) -> Dict[str, Any]:
        """Calculates active trading sessions, overlap status, and session modifiers."""
        now = dt or clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # DST-aware time zones
        tokyo_tz = ZoneInfo("Asia/Tokyo")
        london_tz = ZoneInfo("Europe/London")
        ny_tz = ZoneInfo("America/New_York")

        tokyo_now = now.astimezone(tokyo_tz)
        london_now = now.astimezone(london_tz)
        ny_now = now.astimezone(ny_tz)

        sessions = []
        if 9 <= tokyo_now.hour < 18:
            sessions.append("Tokyo")
        if 8 <= london_now.hour < 16 or (london_now.hour == 16 and london_now.minute <= 30):
            sessions.append("London")
        if 8 <= ny_now.hour < 17:
            sessions.append("New York")

        overlap = "London-NY" if ("London" in sessions and "New York" in sessions) else None
        if not sessions:
            sessions = ["Off-peak"]

        from monika.domain.market.session_info import get_current_market_session

        base_sess = get_current_market_session(now)

        return {
            "utc_time": now.strftime("%H:%M UTC"),
            "current_time_utc": now.strftime("%H:%M:%S"),
            "active_sessions": sessions,
            "overlap": overlap,
            "is_london_ny_overlap": overlap is not None or base_sess.get("is_london_ny_overlap", False),
            "is_off_peak": "Off-peak" in sessions or base_sess.get("is_off_peak", False),
            "highest_liquidity": overlap is not None,
            "session_modifier": 1 if overlap else (-2 if "Off-peak" in sessions else 0),
            "local_times": {
                "Jakarta (WIB)": now.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB"),
                "Tokyo": tokyo_now.strftime("%H:%M JST"),
                "London": london_now.strftime("%H:%M %Z"),
                "New York": ny_now.strftime("%H:%M %Z"),
            },
            "status": "active",
        }

    async def get_economic_calendar(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        """Fetch economic calendar events from database with impact and currency filters."""
        impact_filter = kwargs.get("impact_filter", "high_and_medium")
        currency_filter = kwargs.get("currency_filter", "")
        hours_ahead = kwargs.get("hours_ahead", 48)
        hours_behind = kwargs.get("hours_behind", 24)

        now = clock.now()
        since = now - timedelta(hours=hours_behind)
        until = now + timedelta(hours=hours_ahead)

        if session:
            try:
                from monika.infrastructure.database.models import EconomicCalendar

                query = (
                    select(EconomicCalendar)
                    .where(EconomicCalendar.event_time >= since)
                    .where(EconomicCalendar.event_time <= until)
                    .order_by(EconomicCalendar.event_time.asc())
                    .limit(100)
                )
                if impact_filter == "high":
                    query = query.where(EconomicCalendar.impact == "high")
                elif impact_filter == "medium":
                    query = query.where(EconomicCalendar.impact == "medium")
                elif impact_filter == "high_and_medium":
                    query = query.where(EconomicCalendar.impact.in_(["high", "medium"]))

                if currency_filter:
                    raw_currs = [c.strip().upper() for c in currency_filter.split(",") if c.strip()]
                    expanded_currs = set(raw_currs)
                    if "AUD" in expanded_currs:
                        expanded_currs.add("AU")
                    if "AU" in expanded_currs:
                        expanded_currs.add("AUD")
                    if "GBP" in expanded_currs:
                        expanded_currs.add("UK")
                    if "UK" in expanded_currs:
                        expanded_currs.add("GBP")
                    if "JPY" in expanded_currs:
                        expanded_currs.add("JP")
                    if "EUR" in expanded_currs:
                        expanded_currs.add("EU")
                    query = query.where(EconomicCalendar.currency.in_(list(expanded_currs)))

                lock = getattr(session, "_session_lock", None)
                if lock is not None:
                    async with lock:
                        rows = (await session.execute(query)).scalars().all()
                else:
                    rows = (await session.execute(query)).scalars().all()
                if rows:

                    def _is_past_event(r_time, curr_now):
                        if isinstance(r_time, datetime) and isinstance(curr_now, datetime):
                            if r_time.tzinfo is None and curr_now.tzinfo is not None:
                                r_time = r_time.replace(tzinfo=timezone.utc)
                            elif r_time.tzinfo is not None and curr_now.tzinfo is None:
                                curr_now = curr_now.replace(tzinfo=timezone.utc)
                            return r_time <= curr_now
                        return False

                    from monika.application.scheduler.post_release_analyzer import CURRENCY_TO_SYMBOLS

                    wib_tz = ZoneInfo("Asia/Jakarta")

                    def _fmt_wib(dt_val):
                        if not dt_val:
                            return None
                        if dt_val.tzinfo is None:
                            dt_val = dt_val.replace(tzinfo=timezone.utc)
                        return dt_val.astimezone(wib_tz).strftime("%Y-%m-%d %H:%M WIB")

                    return {
                        "count": len(rows),
                        "events": [
                            {
                                "event_name": f"<untrusted_external_content>{_html.escape(r.event_name or '')}</untrusted_external_content>",
                                "currency": r.currency,
                                "country": getattr(r, "country", ""),
                                "impact": r.impact,
                                "actual": r.actual if _is_past_event(r.event_time, now) else None,
                                "forecast": r.forecast,
                                "previous": r.previous,
                                "event_time": r.event_time.isoformat() if r.event_time is not None else None,
                                "event_time_wib": _fmt_wib(r.event_time),
                                "affected_pairs": CURRENCY_TO_SYMBOLS.get((r.currency or "").upper(), []),
                                "surprise_score": getattr(r, "surprise_score", None),
                            }
                            for r in rows
                        ],
                    }
            except Exception as e:
                logger.warning(f"Database economic calendar query error: {e}")

        # Fallback to live calendar scraper if DB empty or no session.
        # Gated + time-bounded: an unconstrained DrissionPage/Chrome scrape can block
        # the caller (Stage 1 prefetch) indefinitely when the browser is unavailable.
        allow_live_scraper = bool(
            (self.settings.get("data_sources", {}) or {}).get("calendar", {}).get("allow_live_scraper", False)
        )
        if not allow_live_scraper:
            logger.info(
                "Economic calendar DB empty and live scraper disabled (data_sources.calendar.allow_live_scraper=false)."
            )
            return {"events": [], "count": 0, "source": "db_only"}
        try:
            import asyncio

            from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_investing import (
                InvestingCalendarScraper,
            )

            scraper = InvestingCalendarScraper()
            loop = asyncio.get_running_loop()
            timeout_s = float(
                (self.settings.get("data_sources", {}) or {}).get("calendar", {}).get("scraper_timeout_seconds", 45)
            )
            raw_events = await asyncio.wait_for(loop.run_in_executor(None, scraper.fetch_events), timeout=timeout_s)
            events = [e.__dict__ if hasattr(e, "__dict__") else e for e in raw_events]
            return {"events": events, "count": len(events)}
        except Exception as e:
            logger.warning(f"Investing calendar scraper fallback failed: {e}")
            return {"events": [], "count": 0, "error": str(e)}

    async def get_cot_report(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.infrastructure.data_ingestion.sources.cftc_cot import CFTCCOTFetcher

        if kwargs.get("fetch"):
            if session:
                try:
                    fetcher = CFTCCOTFetcher(session, config=self.settings.get("data_sources", {}).get("cftc_cot", {}))
                    count = await fetcher.fetch_all()
                    return {"status": "success", "new_records": count, "markets": kwargs.get("markets", [])}
                except Exception as e:
                    logger.warning(f"COT report fetch failed: {e}")
            return {"markets": kwargs.get("markets", []), "status": "unavailable"}
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_cot_report

        return await handle_get_cot_report(kwargs, session=session, settings=self.settings)

    async def get_bond_yield_spreads(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.infrastructure.data_ingestion.sources.bond_yields_fetcher import BondYieldFetcher

        if kwargs.get("fetch"):
            if session:
                try:
                    fetcher = BondYieldFetcher(session)
                    count = await fetcher.fetch()
                    return {"status": "success", "new_records": count}
                except Exception as e:
                    logger.warning(f"Bond yield fetch failed: {e}")
            return {"status": "unavailable"}
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_bond_yield_spreads

        return await handle_get_bond_yield_spreads(kwargs, session=session, settings=self.settings)

    async def get_vix(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.infrastructure.data_ingestion.sources.vix_yfinance import VIXFetcher

        if kwargs.get("fetch"):
            if session:
                try:
                    fetcher = VIXFetcher(session)
                    count = await fetcher.fetch()
                    return {"status": "success", "new_records": count}
                except Exception as e:
                    logger.warning(f"VIX fetch failed: {e}")
            return {"status": "unavailable"}
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_vix

        return await handle_get_vix(kwargs, session=session, settings=self.settings)

    async def get_dxy(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.infrastructure.data_ingestion.sources.dxy_yfinance import DXYFetcher

        if kwargs.get("fetch"):
            if session:
                try:
                    fetcher = DXYFetcher(session)
                    count = await fetcher.fetch()
                    return {"status": "success", "new_records": count}
                except Exception as e:
                    logger.warning(f"DXY fetch failed: {e}")
            return {"status": "unavailable"}
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_dxy

        return await handle_get_dxy(kwargs, session=session, settings=self.settings)

    async def get_funding_rate(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_funding_rate

        return await handle_get_funding_rate(kwargs, session=session, settings=self.settings)

    async def get_fedwatch_probabilities(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_fedwatch_probabilities

        return await handle_get_fedwatch_probabilities(kwargs, session=session, settings=self.settings)

    async def get_treasury_yields(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_treasury_yields

        return await handle_get_treasury_yields(kwargs, session=session, settings=self.settings)

    async def get_interest_rates(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_interest_rates

        return await handle_get_interest_rates(kwargs, session=session, settings=self.settings)

    async def get_precomputed_cot_signals(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_precomputed_cot_signals

        return await handle_get_precomputed_cot_signals(kwargs, session=session, settings=self.settings)

    async def get_surprise_summary(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_surprise_summary

        return await handle_get_surprise_summary(kwargs, session=session, settings=self.settings)

    async def get_market_correlations(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.trade_intel import handle_get_market_correlations

        return await handle_get_market_correlations(kwargs, session=session)

    async def get_indonesia_macro(self, session: Optional[AsyncSession] = None, **kwargs) -> Dict[str, Any]:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_indonesia_macro

        return await handle_get_indonesia_macro(kwargs, session=session, settings=self.settings)
