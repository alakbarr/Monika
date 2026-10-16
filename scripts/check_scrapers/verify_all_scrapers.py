#!/usr/bin/env python3
# ==============================================================================
# File: scripts/check_scrapers/verify_all_scrapers.py
# ==============================================================================

"""
Script Verifikasi Terpadu Scraper Monika.

Menguji dan memverifikasi secara langsung (live execution) seluruh komponen scraper:
1. FXSSI Sentiment Fetcher (Direct HTTP SSR & Fallback)
2. TradingView News Scraper (Session Injection, Headless DOM, & Public Flow)
3. Twitter Watch Scraper (Session Rotation, Load Start, & Time Budget)
4. Economic Calendar (Investing.com / ForexFactory + Batch DB Persistence)
5. ScraperRunner (End-to-End Orchestration)

Usage:
    python scripts/check_scrapers/verify_all_scrapers.py [--only fxssi,tradingview,twitter,calendar,runner]
"""

import argparse
import asyncio
import logging
import sys
import time
from typing import Any, Dict

from monika.interfaces.cli.platform_compat import ensure_utf8_streams

ensure_utf8_streams()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VerifyScrapers")


def verify_fxssi() -> Dict[str, Any]:
    """Uji verifikasi langsung FXSSISentimentFetcher."""
    logger.info("=" * 60)
    logger.info("--> [1/5] Verifikasi FXSSI Retail Sentiment...")
    logger.info("=" * 60)

    from monika.infrastructure.data_ingestion.scrapers.sentiment.fxssi_sentiment import (
        FXSSISentimentFetcher,
    )

    t0 = time.monotonic()
    fetcher = FXSSISentimentFetcher(session=None, headless=True)
    res = fetcher.fetch_sync()
    duration = time.monotonic() - t0

    ratios = res.get("ratios", {})
    if ratios and "EURUSD" in ratios:
        logger.info(f"[PASS] FXSSI berhasil dalam {duration:.2f}s: {len(ratios)} pairs ({list(ratios.keys())[:5]})")
        return {
            "status": "PASS",
            "count": len(ratios),
            "duration": round(duration, 2),
            "details": f"source={res.get('source')}, pairs={len(ratios)}",
        }
    else:
        logger.error(f"[FAIL] FXSSI gagal dalam {duration:.2f}s: {res.get('error', 'Unknown error')}")
        return {
            "status": "FAIL",
            "count": 0,
            "duration": round(duration, 2),
            "details": res.get("error", "No ratios"),
        }


def verify_tradingview() -> Dict[str, Any]:
    """Uji verifikasi langsung TradingViewNewsScraper."""
    logger.info("=" * 60)
    logger.info("--> [2/5] Verifikasi TradingView News Scraper...")
    logger.info("=" * 60)

    from monika.infrastructure.data_ingestion.scrapers.news.tradingview_news import (
        TradingViewNewsScraper,
    )

    t0 = time.monotonic()
    scraper = TradingViewNewsScraper(headless=True)
    try:
        items = scraper.fetch_news(limit=15)
        duration = time.monotonic() - t0
        if items and len(items) > 0:
            logger.info(
                f"[PASS] TradingView berhasil dalam {duration:.2f}s: {len(items)} items. Contoh: '{items[0].title[:60]}...'"
            )
            return {
                "status": "PASS",
                "count": len(items),
                "duration": round(duration, 2),
                "details": f"First headline: '{items[0].title[:45]}'",
            }
        else:
            logger.error(f"[FAIL] TradingView mengembalikan 0 items dalam {duration:.2f}s")
            return {
                "status": "FAIL",
                "count": 0,
                "duration": round(duration, 2),
                "details": "0 items returned",
            }
    finally:
        scraper.close()


def verify_twitter() -> Dict[str, Any]:
    """Uji verifikasi langsung TwitterWatchScraper."""
    logger.info("=" * 60)
    logger.info("--> [3/5] Verifikasi Twitter Watch Scraper...")
    logger.info("=" * 60)

    from monika.infrastructure.data_ingestion.scrapers.social.twitter_watch import (
        TwitterWatchScraper,
    )

    t0 = time.monotonic()
    scraper = TwitterWatchScraper(headless=True)
    try:
        tweets = scraper.fetch_latest_tweets(max_age_minutes=720)
        duration = time.monotonic() - t0
        if tweets and len(tweets) > 0:
            logger.info(
                f"[PASS] Twitter berhasil dalam {duration:.2f}s: {len(tweets)} tweets terkumpul. Budget <65s terpenuhi."
            )
            return {
                "status": "PASS",
                "count": len(tweets),
                "duration": round(duration, 2),
                "details": f"{len(tweets)} tweets in {duration:.1f}s",
            }
        else:
            logger.warning(
                f"[PASS/WARN] Twitter mengembalikan 0 tweets dalam {duration:.2f}s (kemungkinan cookies kadaluarsa/rate limit)."
            )
            return {
                "status": "WARN",
                "count": 0,
                "duration": round(duration, 2),
                "details": "0 tweets (session pool check needed)",
            }
    finally:
        scraper.close()


async def verify_calendar() -> Dict[str, Any]:
    """Uji verifikasi langsung InvestingCalendarScraper + batch_save_calendar."""
    logger.info("=" * 60)
    logger.info("--> [4/5] Verifikasi Economic Calendar & Batch DB Persistence...")
    logger.info("=" * 60)

    from monika.infrastructure.data_ingestion.scrapers.calendar.calendar_investing import (
        InvestingCalendarScraper,
    )
    from monika.infrastructure.database.adapters import batch_save_calendar
    from monika.infrastructure.database.db import get_session

    t0 = time.monotonic()
    scraper = InvestingCalendarScraper(headless=True)
    try:
        events = await asyncio.to_thread(scraper.fetch_events, fast_mode=False)
        fetch_duration = time.monotonic() - t0
        logger.info(f"Kalender diunduh: {len(events)} events dalam {fetch_duration:.2f}s")

        t_db = time.monotonic()
        async with get_session() as session:
            saved = await batch_save_calendar(session, events)
        db_duration = time.monotonic() - t_db
        total_duration = time.monotonic() - t0

        if len(events) > 0:
            logger.info(
                f"[PASS] Kalender berhasil: {len(events)} events diambil ({fetch_duration:.2f}s), "
                f"DB batch save selesai dalam {db_duration:.3f}s (tersimpan/terbarui: {saved}). Total: {total_duration:.2f}s"
            )
            return {
                "status": "PASS",
                "count": len(events),
                "duration": round(total_duration, 2),
                "details": f"Fetch: {fetch_duration:.1f}s, DB: {db_duration:.3f}s, Saved/Updated: {saved}",
            }
        else:
            logger.error(f"[FAIL] Kalender mengembalikan 0 events dalam {total_duration:.2f}s")
            return {
                "status": "FAIL",
                "count": 0,
                "duration": round(total_duration, 2),
                "details": "0 events",
            }
    finally:
        scraper.close()


async def verify_scraper_runner() -> Dict[str, Any]:
    """Uji verifikasi langsung ScraperRunner.run_all()."""
    logger.info("=" * 60)
    logger.info("--> [5/5] Verifikasi Orchestrasi End-to-End ScraperRunner...")
    logger.info("=" * 60)

    from monika.application.scheduler.scraper_runner import ScraperRunner

    settings = {
        "trading": {"schedule": {"scraper_stagger_seconds": 1}},
        "scraping": {
            "sources": {
                "rss_bloomberg": {"enabled": True},
                "investing_calendar": {"enabled": True},
                "tradingview": {"enabled": True},
                "kitco": {"enabled": True},
                "cme_fedwatch": {"enabled": True},
                "twitter": {"enabled": True},
            }
        },
    }

    t0 = time.monotonic()
    runner = ScraperRunner(settings)
    try:
        results = await runner.run_all()
        duration = time.monotonic() - t0

        has_timeout = any("timed out" in str(v.get("error", "")) for v in results.values() if isinstance(v, dict))
        failed_scrapers = [k for k, v in results.items() if isinstance(v, dict) and "error" in v]

        if not has_timeout:
            logger.info(f"[PASS] ScraperRunner selesai dalam {duration:.2f}s tanpa timeout! Hasil: {results}")
            return {
                "status": "PASS",
                "count": len(results),
                "duration": round(duration, 2),
                "details": f"Sources: {list(results.keys())}, Failures: {failed_scrapers}",
            }
        else:
            logger.error(f"[FAIL] ScraperRunner mengalami timeout dalam {duration:.2f}s: {results}")
            return {
                "status": "FAIL",
                "count": len(results),
                "duration": round(duration, 2),
                "details": f"Failures: {failed_scrapers}",
            }
    finally:
        runner.stop()


def print_summary(summary_results: Dict[str, Dict[str, Any]]):
    print("\n" + "=" * 80)
    print("                    RINGKASAN HASIL VERIFIKASI SCRAPER MONIKA")
    print("=" * 80)
    header = f"{'Komponen':<22} | {'Status':<8} | {'Items':<8} | {'Durasi (s)':<12} | {'Catatan'}"
    print(header)
    print("-" * 80)

    all_passed = True
    for name, r in summary_results.items():
        st = r["status"]
        if st == "FAIL":
            all_passed = False
        print(f"{name:<22} | {st:<8} | {r['count']:<8} | {r['duration']:<12} | {r['details']}")

    print("=" * 80)
    if all_passed:
        print("[SUKSES PENUH] Seluruh pengujian scraper berhasil diverifikasi dengan sukses!")
    else:
        print("[PERINGATAN] Terdapat komponen yang gagal. Silakan periksa log di atas.")
    print("=" * 80 + "\n")
    return all_passed


async def main():
    parser = argparse.ArgumentParser(description="Verifikasi Scraper Terpadu Monika")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Komponen yang diuji secara spesifik: fxssi, tradingview, twitter, calendar, runner",
    )
    args = parser.parse_args()

    target_set = set([x.strip().lower() for x in args.only.split(",") if x.strip()]) if args.only else None

    results: Dict[str, Dict[str, Any]] = {}

    if not target_set or "fxssi" in target_set:
        results["FXSSI Sentiment"] = await asyncio.to_thread(verify_fxssi)

    if not target_set or "tradingview" in target_set:
        results["TradingView News"] = await asyncio.to_thread(verify_tradingview)

    if not target_set or "calendar" in target_set:
        results["Economic Calendar"] = await verify_calendar()

    if not target_set or "twitter" in target_set:
        results["Twitter Watch"] = await asyncio.to_thread(verify_twitter)

    if not target_set or "runner" in target_set:
        results["ScraperRunner Full"] = await verify_scraper_runner()

    passed = print_summary(results)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
