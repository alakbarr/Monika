# ==============================================================================
# File: scheduler/scraper_runner.py
# ==============================================================================

"""
Scraper Runner: Eksekutor periodik seluruh scraper (data disimpan ke DB).
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from database.db import get_session
from database.adapters import batch_save_news, batch_save_calendar, batch_save_tweets, batch_save_fedwatch

logger = logging.getLogger("TradingAgent.ScraperRunner")


DEFAULT_SCRAPER_TIMEOUTS: dict[str, float] = {
    "calendar": 180.0,
    "fedwatch": 120.0,
    "tradingview": 90.0,
    "kitco": 90.0,
    "twitter": 90.0,
    "rss": 60.0,
}


class ScraperRunner:
    """
    Menjalankan scraper (news, calendar, social, macro) dengan antrean dan delay (stagger)
    agar terhindar dari rate-limit. Melacak kegagalan scraper & mengirim notifikasi Telegram.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self._running = True
        self._stop_requested = False
        sched_cfg = settings.get("trading", {}).get("schedule", {})
        self.scraper_stagger = sched_cfg.get("scraper_stagger_seconds", 10)
        scraping_cfg = settings.get("scraping", {})
        sources_cfg = scraping_cfg.get("sources", {})
        self.enabled_sources = sources_cfg
        self.failure_alert_threshold: int = int(scraping_cfg.get("consecutive_failure_alert", 3))
        # Track consecutive failures per scraper name
        self._consecutive_failures: dict[str, int] = {}
        import threading
        self._scrapers_lock = threading.Lock()
        self._active_scrapers: set = set()
        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scraper_runner")

    def _register_scraper(self, scraper):
        with self._scrapers_lock:
            self._active_scrapers.add(scraper)
        return scraper

    def _unregister_scraper(self, scraper):
        with self._scrapers_lock:
            self._active_scrapers.discard(scraper)

    def _cleanup_timed_out_scrapers(self) -> int:
        """
        Forcibly closes all currently active scrapers and kills their process trees.
        Returns the number of scrapers cleaned up.
        """
        with self._scrapers_lock:
            scrapers_to_close = list(self._active_scrapers)
            self._active_scrapers.clear()

        cleaned = 0
        for scraper in scrapers_to_close:
            try:
                pid = getattr(scraper, "browser_pid", None)
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                    from scrapers.base_scraper import kill_process_tree
                    kill_process_tree(pid)
                if hasattr(scraper, "close"):
                    scraper.close()
                cleaned += 1
            except Exception as e:
                logger.debug(f"Error closing active scraper during cleanup: {e}")
        return cleaned

    async def run_all(self) -> dict:
        """
        Menjalankan seluruh scraper aktif secara bergiliran.

        Returns:
            Dict hasil scraping per sumber.
        """
        if self._stop_requested or not self._running:
            return {}
        results = {}

        # Jalankan scraper news RSS (lebih ringan, tidak buka browser per artikel)
        if not self._running:
            return results
        results["rss"] = await self._run_rss_scrapers()

        # Stagger sebelum browser scrapers
        if not self._running:
            return results
        await asyncio.sleep(self.scraper_stagger)

        # Calendar
        if not self._running:
            return results
        if self.enabled_sources.get("investing_calendar", {}).get("enabled", True):
            results["calendar"] = await self._run_single("calendar", self._fetch_calendar)
            if not self._running:
                return results
            await asyncio.sleep(self.scraper_stagger)

        # TradingView news
        if not self._running:
            return results
        if self.enabled_sources.get("tradingview", {}).get("enabled", True):
            results["tradingview"] = await self._run_single("tradingview", self._fetch_tradingview)
            if not self._running:
                return results
            await asyncio.sleep(self.scraper_stagger)

        # Kitco news
        if not self._running:
            return results
        if self.enabled_sources.get("kitco", {}).get("enabled", True):
            results["kitco"] = await self._run_single("kitco", self._fetch_kitco)
            if not self._running:
                return results
            await asyncio.sleep(self.scraper_stagger)

        # FedWatch
        if not self._running:
            return results
        if self.enabled_sources.get("cme_fedwatch", {}).get("enabled", True):
            results["fedwatch"] = await self._run_single("fedwatch", self._fetch_fedwatch)
            if not self._running:
                return results
            await asyncio.sleep(self.scraper_stagger)

        # Twitter (optional, lower priority)
        if not self._running:
            return results
        if self.enabled_sources.get("twitter", {}).get("enabled", True):
            results["twitter"] = await self._run_single("twitter", self._fetch_twitter)

        logger.info(f"ScraperRunner complete: {results}")
        return results

    # ------------------------------------------------------------------
    # Generic single-scraper runner with consecutive-failure tracking
    # ------------------------------------------------------------------

    async def _run_single(self, name: str, fetch_fn) -> dict:
        """
        Mengeksekusi satu scraper, menghitung error beruntun, dan notifikasi bila perlu.

        Returns:
            Dict hasil fetch atau error message.
        """
        if not self._running:
            return {"skipped": "shutdown"}
        timeout_sec = DEFAULT_SCRAPER_TIMEOUTS.get(name, 90.0)
        try:
            # Timeout per jenis scraper untuk mencegah zombie tasks
            result = await asyncio.wait_for(fetch_fn(), timeout=timeout_sec)
            # Success: reset failure counter
            if name in self._consecutive_failures:
                if self._consecutive_failures[name] >= self.failure_alert_threshold:
                    logger.info(f"Scraper '{name}' recovered after {self._consecutive_failures[name]} consecutive failures.")
                del self._consecutive_failures[name]
            return result
        except asyncio.TimeoutError:
            self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1
            count = self._consecutive_failures[name]
            logger.warning(f"Scraper '{name}' timed out after {int(timeout_sec)}s (consecutive: {count}).")
            cleaned = self._cleanup_timed_out_scrapers()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} active scraper process tree(s) after timeout on '{name}'.")
            if count >= 3:
                try:
                    old_executor = self._executor
                    self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scraper_runner")
                    old_executor.shutdown(wait=False, cancel_futures=True)
                    logger.info(f"Re-initialized ScraperRunner thread pool after repeated timeouts on '{name}'.")
                except Exception as ex_err:
                    logger.debug(f"Failed to recycle executor: {ex_err}")
            return {"error": f"Scraper '{name}' timed out after {int(timeout_sec)}s", "consecutive_failures": count}
        except Exception as e:
            self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1
            count = self._consecutive_failures[name]
            logger.error(f"Scraper '{name}' failed (consecutive: {count}): {e}")

            if count == self.failure_alert_threshold:
                msg = (
                    f"⚠️ <b>Scraper Alert</b>\n"
                    f"Scraper <code>{name}</code> has failed {count} times consecutively.\n"
                    f"Error: {str(e)[:200]}\n"
                    f"Check scraper logs or website availability."
                )
                logger.warning(f"Scraper '{name}' consecutive failure threshold reached ({count}). Alerting admin.")
                try:
                    from utils.infra.notifier import AgentNotifier
                    notifier = AgentNotifier()
                    await notifier.send_warning(msg)
                except Exception as notify_err:
                    logger.warning(f"Could not send scraper failure alert: {notify_err}")

            return {"error": str(e), "consecutive_failures": count}

    async def _run_in_executor(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    def stop(self) -> None:
        """Shutdown thread pool executor and forcibly close all active scrapers."""
        self._running = False
        self._stop_requested = True
        self._cleanup_timed_out_scrapers()

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.debug(f"Error shutting down scraper executor: {e}")

    # ------------------------------------------------------------------
    # Fetch implementations (sync code wrapped in executor)
    # ------------------------------------------------------------------

    async def _fetch_calendar(self) -> dict:
        events = []
        source = "investing"

        def _fetch_investing():
            from scrapers.calendar.calendar_investing import InvestingCalendarScraper
            scraper = self._register_scraper(InvestingCalendarScraper(headless=True))
            try:
                return scraper.fetch_events()
            finally:
                self._unregister_scraper(scraper)
                scraper.close()

        # 1. Coba Investing.com (Provider Utama, timeout 90s)
        try:
            events = await asyncio.wait_for(self._run_in_executor(_fetch_investing), timeout=90.0)
        except (asyncio.TimeoutError, Exception) as inv_err:
            inv_err_msg = type(inv_err).__name__ if not str(inv_err) else f"{type(inv_err).__name__}: {inv_err}"
            logger.warning(f"InvestingCalendarScraper failed or timed out: {inv_err_msg}")
            events = []

        # 2. Coba ForexFactory (Fallback Utama, timeout 45s)
        if not events:
            logger.warning("InvestingCalendarScraper returned 0 events — activating ForexFactory fallback")
            def _fetch_ff():
                from scrapers.calendar.calendar_forexfactory import ForexFactoryCalendarScraper
                scraper = self._register_scraper(ForexFactoryCalendarScraper(headless=True))
                try:
                    return scraper.fetch_events()
                finally:
                    self._unregister_scraper(scraper)
                    scraper.close()
            
            try:
                events = await asyncio.wait_for(self._run_in_executor(_fetch_ff), timeout=45.0)
                if events:
                    logger.info(f"ForexFactory fallback: got {len(events)} events")
                    source = "forexfactory"
            except (asyncio.TimeoutError, Exception) as ff_err:
                ff_err_msg = type(ff_err).__name__ if not str(ff_err) else f"{type(ff_err).__name__}: {ff_err}"
                logger.error(f"ForexFactory fallback failed or timed out: {ff_err_msg}")
                events = []

        # 3. Coba Finnhub (Fallback Sekunder API, timeout 15s)
        if not events:
            logger.warning("ForexFactory fallback returned 0 events — activating Finnhub fallback")
            try:
                from scrapers.calendar.calendar_finnhub import FinnhubCalendarScraper
                scraper = FinnhubCalendarScraper()
                if hasattr(scraper, "afetch_today_events"):
                    events = await asyncio.wait_for(scraper.afetch_today_events(), timeout=15.0)
                else:
                    events = await asyncio.wait_for(self._run_in_executor(scraper.fetch_today_events), timeout=15.0)
                if events:
                    logger.info(f"Finnhub fallback: got {len(events)} events")
                    source = "finnhub"
            except Exception as finnhub_err:
                logger.error(f"Finnhub fallback failed: {finnhub_err}")
                events = []

        async with get_session() as session:
            n = await batch_save_calendar(session, events)
        if n == 0 and not events:
            now_utc = datetime.now(timezone.utc)
            if now_utc.weekday() < 5:
                raise RuntimeError("All calendar scraper sources failed to return events")
        return {"saved": n, "source": source}


    async def _fetch_tradingview(self) -> dict:
        def _fetch():
            from scrapers.news.tradingview_news import TradingViewNewsScraper
            scraper = self._register_scraper(TradingViewNewsScraper(headless=True))
            try:
                return scraper.fetch_news(limit=15)
            finally:
                self._unregister_scraper(scraper)
                scraper.close()

        news_items = await self._run_in_executor(_fetch)
        async with get_session() as session:
            n = await batch_save_news(session, news_items)
        if n == 0 and not news_items:
            now_utc = datetime.now(timezone.utc)
            if now_utc.weekday() < 5:
                raise RuntimeError("TradingView scraper returned 0 items during active market window")
        return {"saved": n}

    async def _fetch_kitco(self) -> dict:
        def _fetch():
            from scrapers.news.kitco_news import KitcoNewsScraper
            scraper = self._register_scraper(KitcoNewsScraper(headless=True))
            try:
                return scraper.fetch_news(limit=15)
            finally:
                self._unregister_scraper(scraper)
                scraper.close()

        news_items = await self._run_in_executor(_fetch)
        async with get_session() as session:
            n = await batch_save_news(session, news_items)
        if n == 0 and not news_items:
            now_utc = datetime.now(timezone.utc)
            if now_utc.weekday() < 5:
                raise RuntimeError("Kitco scraper returned 0 items during active market window")
        return {"saved": n}

    async def _fetch_fedwatch(self) -> dict:
        def _fetch():
            from scrapers.macro.cme_fedwatch import FedWatchScraper
            scraper = self._register_scraper(FedWatchScraper(headless=True))
            try:
                return scraper.fetch_probabilities()
            finally:
                self._unregister_scraper(scraper)
                scraper.close()

        meetings = await self._run_in_executor(_fetch)
        async with get_session() as session:
            n = await batch_save_fedwatch(session, meetings)
        if n == 0 and not meetings:
            now_utc = datetime.now(timezone.utc)
            if now_utc.weekday() < 5:
                raise RuntimeError("CME FedWatch scraper returned 0 meetings during active market window")
        return {"saved": n}

    async def _fetch_twitter(self) -> dict:
        def _fetch():
            from scrapers.social.twitter_watch import TwitterWatchScraper
            list_url = self.enabled_sources.get("twitter", {}).get("list_url")
            scraper = self._register_scraper(TwitterWatchScraper(headless=True, list_url=list_url))
            try:
                return scraper.fetch_latest_tweets(max_age_minutes=360)
            finally:
                self._unregister_scraper(scraper)
                scraper.close()

        tweets = await self._run_in_executor(_fetch)
        async with get_session() as session:
            n = await batch_save_tweets(session, tweets)
        if n == 0 and not tweets:
            now_utc = datetime.now(timezone.utc)
            if now_utc.weekday() < 5:
                raise RuntimeError("Twitter watch scraper returned 0 tweets during active market window")
        return {"saved": n}

    # ------------------------------------------------------------------
    # RSS scrapers (dikelompokkan — dilacak sebagai satu unit "rss")
    # ------------------------------------------------------------------

    async def _run_rss_scrapers(self) -> dict:
        from scrapers.news.rss_bloomberg import BloombergRssScraper
        from scrapers.news.rss_wsj import WsjRssScraper
        from scrapers.news.rss_marketwatch import MarketwatchRssScraper
        from scrapers.news.rss_dow_jones import DowJonesRssScraper
        from scrapers.news.rss_forexlive import ForexliveRssScraper
        from scrapers.news.rss_fxstreet import FxstreetRssScraper
        from scrapers.news.rss_investing import InvestingRssScraper
        from scrapers.news.rss_coindesk import CoindeskRssScraper
        from scrapers.news.rss_reuters import ReutersRssScraper
        from scrapers.news.rss_cnbc import CnbcRssScraper
        from scrapers.news.rss_ft import FinancialTimesRssScraper
        # Feed resmi bank sentral — prioritas tertinggi, tanpa risiko pemblokiran scraping
        from scrapers.news.rss_fed import FedRssScraper
        from scrapers.news.rss_ecb import EcbRssScraper
        from scrapers.news.rss_boe import BoeRssScraper
        from scrapers.news.rss_boj import BojRssScraper
        from scrapers.news.rss_rba import RbaRssScraper

        rss_classes = [
            # Feed resmi bank sentral — prioritas tertinggi, aktif secara default
            ("fed_official",  FedRssScraper,         self.enabled_sources.get("rss_fed", {}).get("enabled", True)),
            ("ecb_official",  EcbRssScraper,         self.enabled_sources.get("rss_ecb", {}).get("enabled", True)),
            ("boe_official",  BoeRssScraper,         self.enabled_sources.get("rss_boe", {}).get("enabled", True)),
            ("boj_official",  BojRssScraper,         self.enabled_sources.get("rss_boj", {}).get("enabled", True)),
            ("rba_official",  RbaRssScraper,         self.enabled_sources.get("rss_rba", {}).get("enabled", True)),
            # Berita finansial pihak ketiga
            ("bloomberg",     BloombergRssScraper,   self.enabled_sources.get("rss_bloomberg", {}).get("enabled", True)),
            ("wsj",           WsjRssScraper,         self.enabled_sources.get("rss_wsj", {}).get("enabled", True)),
            ("marketwatch",   MarketwatchRssScraper, self.enabled_sources.get("rss_marketwatch", {}).get("enabled", True)),
            ("dow_jones",     DowJonesRssScraper,    self.enabled_sources.get("rss_dow_jones", {}).get("enabled", True)),
            ("forexlive",     ForexliveRssScraper,   self.enabled_sources.get("rss_forexlive", {}).get("enabled", True)),
            ("fxstreet",      FxstreetRssScraper,    self.enabled_sources.get("rss_fxstreet", {}).get("enabled", True)),
            ("investing",     InvestingRssScraper,   self.enabled_sources.get("rss_investing", {}).get("enabled", True)),
            ("coindesk",      CoindeskRssScraper,    self.enabled_sources.get("rss_coindesk", {}).get("enabled", True)),
            ("reuters",       ReutersRssScraper,     self.enabled_sources.get("rss_reuters", {}).get("enabled", True)),
            ("cnbc",          CnbcRssScraper,        self.enabled_sources.get("rss_cnbc", {}).get("enabled", True)),
            ("ft",            FinancialTimesRssScraper, self.enabled_sources.get("rss_ft", {}).get("enabled", True)),
        ]


        total_saved = 0
        for name, cls, enabled in rss_classes:
            if not self._running:
                break
            if not enabled:
                continue
            rss_name = f"rss_{name}"
            try:
                def _fetch(klass=cls):
                    scraper = self._register_scraper(klass())
                    try:
                        return scraper.fetch_news(limit=15)
                    finally:
                        self._unregister_scraper(scraper)
                        scraper.close()

                # NEW: Timeout for RSS fetchers to prevent stalls
                news_items = await asyncio.wait_for(self._run_in_executor(_fetch), timeout=30.0)
                async with get_session() as session:
                    n = await batch_save_news(session, news_items)
                    total_saved += n
                logger.info(f"RSS {name}: {n} items saved")
                # Reset failure count only on actual data fetch
                if news_items and rss_name in self._consecutive_failures:
                    del self._consecutive_failures[rss_name]
            except Exception as e:
                self._consecutive_failures[rss_name] = self._consecutive_failures.get(rss_name, 0) + 1
                count = self._consecutive_failures[rss_name]
                logger.error(f"RSS {name} failed (consecutive: {count}): {e}")
                if count == self.failure_alert_threshold:
                    try:
                        from utils.infra.notifier import AgentNotifier
                        notifier = AgentNotifier()
                        await notifier.send_warning(
                            f"⚠️ <b>RSS Scraper Alert</b>\n"
                            f"RSS <code>{name}</code> failed {count} times consecutively.\n"
                            f"Error: {str(e)[:200]}"
                        )
                    except Exception:
                        pass
            await asyncio.sleep(2)

        return {"saved": total_saved}
