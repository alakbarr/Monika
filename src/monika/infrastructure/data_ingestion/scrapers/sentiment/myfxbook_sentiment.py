# ==============================================================================
# File: scrapers/sentiment/myfxbook_sentiment.py
# ==============================================================================

"""
MyFxBook Community Outlook — Data posisi trader ritel untuk Forex & Metals.
Menggunakan DrissionPage melalui BaseScraper.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives import clock
from monika.infrastructure.data_ingestion.scrapers.base_scraper import BaseScraper
from monika.infrastructure.database.models import SystemConfig

logger = logging.getLogger("TradingAgent.MyFxBookSentiment")

SYMBOL_ALIASES = {
    "EURUSD": ["EURUSD", "EUR/USD"],
    "GBPUSD": ["GBPUSD", "GBP/USD"],
    "USDJPY": ["USDJPY", "USD/JPY"],
    "AUDUSD": ["AUDUSD", "AUD/USD"],
    "XAUUSD": ["XAUUSD", "XAU/USD", "GOLD"],
}


class MyFxBookSentimentFetcher:
    def __init__(self, session: AsyncSession, headless=True):
        self.headless = headless
        self.session = session
        self.url = "https://www.myfxbook.com/community/outlook"
        self.symbols = list(SYMBOL_ALIASES.keys())

    def _parse_html(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        results = {}
        for row in soup.find_all("tr"):
            text = row.get_text(separator=" ", strip=True).upper()
            matched_asset = None
            for standard_sym, aliases in SYMBOL_ALIASES.items():
                if any(alias in text for alias in aliases):
                    matched_asset = standard_sym
                    break

            if matched_asset and matched_asset not in results:
                short_match = re.search(r"SHORT.*?(\d+(?:\.\d+)?)%", text, re.IGNORECASE)
                long_match = re.search(r"LONG.*?(\d+(?:\.\d+)?)%", text, re.IGNORECASE)
                if short_match and long_match:
                    results[matched_asset] = {
                        "short_percent": float(short_match.group(1)),
                        "long_percent": float(long_match.group(1)),
                        "long_short_ratio": round(
                            float(long_match.group(1)) / max(float(short_match.group(1)), 0.1), 4
                        ),
                    }
                else:
                    pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
                    if len(pcts) >= 2:
                        results[matched_asset] = {
                            "short_percent": float(pcts[-2]),
                            "long_percent": float(pcts[-1]),
                            "long_short_ratio": round(float(pcts[-1]) / max(float(pcts[-2]), 0.1), 4),
                        }
        return results

    def fetch_sync(self) -> dict:
        result = {"error": "Failed to extract MyFxBook data"}
        ratios = {}
        scraper = None

        try:
            logger.info("Fetching MyFxBook Sentiment via DrissionPage BaseScraper...")
            scraper = BaseScraper(headless=self.headless, profile_name="myfxbook")
            if not scraper or not scraper.page:
                return {"error": "Failed to initialize scraper browser"}

            success = scraper.navigate_with_fallback(
                self.url, wait_selector="css:table.tooltip-bg, table.table-bordered, table", timeout=25
            )
            if success and scraper.page:
                # Tunggu data dimuat
                page_obj: Any = scraper.page
                page_obj.wait(3)
                html = page_obj.html
                ratios = self._parse_html(html)

            if ratios:
                result = {"source": "myfxbook", "ratios": ratios, "fetched_at": clock.now().isoformat()}
            else:
                result = {"error": "All MyFxBook extraction methods failed or returned empty"}
                logger.warning("All MyFxBook extraction methods failed or returned empty")

        except Exception as e:
            logger.warning(f"Error fetching MyFxBook Sentiment: {e}")
            result = {"error": str(e)}
        finally:
            if scraper:
                scraper.close()

        return result

    async def fetch(self) -> dict:
        if clock.is_simulated():
            now_dt = clock.now()
            from monika.infrastructure.database.domain_models.market import PriceOHLCV

            ratios = {}
            for sym in self.symbols:
                bars = (
                    await self.session.execute(
                        select(PriceOHLCV.close, PriceOHLCV.open)
                        .where(PriceOHLCV.symbol == sym)
                        .where(PriceOHLCV.timeframe == "H4")
                        .where(PriceOHLCV.timestamp <= now_dt)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(6)
                    )
                ).all()
                if bars:
                    bull_count = sum(1 for c, o in bars if float(c) >= float(o))
                    retail_long_pct = round(max(20.0, min(80.0, 50.0 - (bull_count - 3) * 6.0)), 1)
                    retail_short_pct = round(100.0 - retail_long_pct, 1)
                    ls_ratio = round(retail_long_pct / max(0.1, retail_short_pct), 4)
                else:
                    retail_long_pct = 50.0
                    retail_short_pct = 50.0
                    ls_ratio = 1.0

                ratios[sym] = {
                    "long_percent": retail_long_pct,
                    "short_percent": retail_short_pct,
                    "long_short_ratio": ls_ratio,
                }

            return {
                "source": "myfxbook",
                "ratios": ratios,
                "fetched_at": now_dt.isoformat(),
            }

        # Jalankan proses scraping DrissionPage di thread terpisah dengan budget timeout lokal 30s
        try:
            async with asyncio.timeout(30.0):
                result = await asyncio.to_thread(self.fetch_sync)
        except TimeoutError, asyncio.TimeoutError:
            logger.warning("MyFxBook sentiment scrape timed out (30s budget exceeded)")
            result = {"error": "Scrape timed out after 30s"}

        # Simpan ke DB hanya jika session tersedia dan ada ratios valid
        if self.session and "ratios" in result and result["ratios"]:
            from monika.infrastructure.database.safe_ops import safe_commit

            cfg_key = "myfxbook_sentiment_latest"
            existing = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))
            ).scalar_one_or_none()

            if existing:
                existing.value = json.dumps(result)
            else:
                self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))
            await safe_commit(self.session, label="MyfxbookSentiment")
        elif self.session and ("error" in result or not result.get("ratios")):
            # Fallback ke cache DB jika scraping gagal/timeout
            try:
                cfg_key = "myfxbook_sentiment_latest"
                cached = (
                    await self.session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))
                ).scalar_one_or_none()
                if cached and cached.value:
                    cached_data = json.loads(cached.value)
                    if isinstance(cached_data, dict) and cached_data.get("ratios"):
                        cached_data["fallback"] = True
                        logger.info(
                            "MyFxBook scrape failed/timed out, serving last known valid sentiment from DB cache."
                        )
                        return cached_data
            except Exception as cache_err:
                logger.debug(f"MyFxBook cache fallback check failed: {cache_err}")

        return result
