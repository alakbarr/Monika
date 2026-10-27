# ==============================================================================
# File: analysis/tools/handlers/macro/calendar.py
# ==============================================================================

"""
Economic calendar, economic surprises, earnings, and macro report handlers.
"""

import html as _html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.macro.base import _get_macro_context, logger
from monika.infrastructure.database.models import EconomicCalendar, SystemConfig


async def handle_get_economic_calendar(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"count": 0, "events": [], "status": "no_session"}

    event_filter = (args.get("event_name") or args.get("query") or args.get("search") or "").strip()
    impact_filter = args.get("impact_filter")
    if not impact_filter:
        impact_filter = "all" if event_filter else "high_and_medium"

    currency_filter = args.get("currency_filter", "")
    hours_ahead = int(args.get("hours_ahead", 48))

    custom_behind = args.get("hours_behind")
    if custom_behind is not None:
        hours_behind = int(custom_behind)
    else:
        hours_behind = 168 if event_filter else 24

    now = clock.now()
    since = now - timedelta(hours=hours_behind)
    until = now + timedelta(hours=hours_ahead)

    query = (
        select(EconomicCalendar)
        .where(EconomicCalendar.event_time >= since)
        .where(EconomicCalendar.event_time <= until)
        .order_by(EconomicCalendar.event_time.asc())
        .limit(100)
    )

    if event_filter:
        query = query.where(EconomicCalendar.event_name.ilike(f"%{event_filter}%"))

    if impact_filter == "high":
        query = query.where(EconomicCalendar.impact == "high")
    elif impact_filter == "medium":
        query = query.where(EconomicCalendar.impact == "medium")
    elif impact_filter == "high_and_medium":
        query = query.where(EconomicCalendar.impact.in_(["high", "medium"]))

    if currency_filter:
        currencies = [c.strip() for c in currency_filter.split(",")]
        query = query.where(EconomicCalendar.currency.in_(currencies))

    rows = (await session.execute(query)).scalars().all()

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


async def handle_get_economic_surprise(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for economic surprise"}

    currency = args.get("currency", "USD")
    days_back = args.get("days_back", 14)
    since = clock.now() - timedelta(days=days_back)

    query = (
        select(EconomicCalendar)
        .where(EconomicCalendar.currency == currency.upper())
        .where(EconomicCalendar.event_time >= since)
        .where(EconomicCalendar.surprise_score.is_not(None))
        .order_by(EconomicCalendar.event_time.desc())
    )
    rows = (await session.execute(query)).scalars().all()

    return {
        "currency": currency.upper(),
        "days_back": days_back,
        "count": len(rows),
        "events": [
            {
                "event_name": f"<untrusted_external_content>{_html.escape(r.event_name or '')}</untrusted_external_content>",
                "event_time": r.event_time.isoformat() if r.event_time is not None else None,
                "impact": r.impact,
                "actual": r.actual,
                "forecast": r.forecast,
                "surprise_score": r.surprise_score,
            }
            for r in rows
        ],
    }


async def handle_get_surprise_summary(args: dict, **ctx) -> dict:
    import json

    session, _, settings = _get_macro_context(args, ctx)
    surprise_data = {}
    if session:
        try:
            stmt = select(SystemConfig).where(
                SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"])
            )
            cfg = (await session.execute(stmt)).scalars().first()
            if cfg and cfg.value:
                parsed = json.loads(cfg.value)
                if isinstance(parsed, dict) and "surprise_summary" in parsed:
                    surprise_data = parsed["surprise_summary"]
        except Exception as e:
            logger.debug(f"Failed fetching precomputed surprise summary from SystemConfig: {e}")

        if not surprise_data:
            try:
                from monika.application.analysis.prefetch.macro_preprocessor import MacroPreprocessor

                preprocessor = MacroPreprocessor(settings=settings)
                surprise_data = await preprocessor.compute_surprise_summary(session)
            except Exception as e:
                logger.warning(f"On-the-fly compute_surprise_summary failed: {e}")

    return {
        "status": "success" if surprise_data else "empty",
        "surprise_summary": surprise_data,
        "count": len(surprise_data) if isinstance(surprise_data, dict) else 0,
    }


async def handle_get_earnings_calendar(args: dict, **ctx) -> dict:
    """Fetch corporate earnings announcements from Finnhub or web search fallback."""
    symbol = args.get("symbol")
    from_date = args.get("from_date")
    to_date = args.get("to_date")
    try:
        from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_finnhub import FinnhubCalendarScraper

        scraper = FinnhubCalendarScraper()
        earnings = await scraper.afetch_earnings_calendar(symbol=symbol, from_date=from_date, to_date=to_date)
        if earnings:
            return {"symbol": symbol, "count": len(earnings), "earnings": earnings[:20], "status": "success"}
    except Exception as e:
        logger.debug(f"Finnhub earnings fetch failed: {e}")

    try:
        import asyncio

        from monika.infrastructure.data_ingestion.sources.web_search import WebSearch

        ws = WebSearch()
        q = f"{symbol or 'US tech stocks'} earnings release date calendar estimates 2026"
        async with asyncio.timeout(5.0):
            res = await ws.search(q, max_results=5)
        return {"symbol": symbol, "results": res, "status": "fallback_web_search"}
    except Exception as err:
        return {"symbol": symbol, "error": str(err), "status": "error"}


async def handle_get_indonesia_macro(args: dict, **ctx) -> dict:
    """Fetch Indonesian macro data including Bank Indonesia (BI Rate), JISDOR USD/IDR, Inflation YoY/MoM, and Trade Balance."""
    from monika.infrastructure.data_ingestion.sources.bps_stats import BPSStatsFetcher

    fetcher = BPSStatsFetcher()
    return await fetcher.fetch_all_idr_macro()


async def handle_inspect_economic_report(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_macro_analyzer import UniversalMacroAnalyzer

    analyzer = UniversalMacroAnalyzer(session)
    report_type = args.get("report_type", "CPI")
    period = args.get("period")
    country = args.get("country", "US")
    currency = args.get("currency", "USD")
    if str(report_type).upper() == "NFP":
        return await analyzer.decompose_labor_market(period=period)
    return await analyzer.decompose_report(report_type=report_type, period=period, country=country, currency=currency)
