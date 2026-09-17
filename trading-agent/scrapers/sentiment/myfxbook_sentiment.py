# ==============================================================================
# File: scrapers/sentiment/myfxbook_sentiment.py
# ==============================================================================

"""
MyFxBook Community Outlook — Data posisi trader ritel untuk Forex & Metals.
Menggunakan DrissionPage melalui BaseScraper.
"""
import logging
import json
import re
from datetime import datetime, timezone
from typing import Any
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig
from scrapers.base_scraper import BaseScraper
import asyncio

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
                        "long_short_ratio": round(float(long_match.group(1)) / max(float(short_match.group(1)), 0.1), 4)
                    }
                else:
                    pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
                    if len(pcts) >= 2:
                        results[matched_asset] = {
                            "short_percent": float(pcts[-2]),
                            "long_percent": float(pcts[-1]),
                            "long_short_ratio": round(float(pcts[-1]) / max(float(pcts[-2]), 0.1), 4)
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
                self.url,
                wait_selector="css:table.tooltip-bg, table.table-bordered, table",
                timeout=25
            )
            if success and scraper.page:
                # Tunggu data dimuat
                page_obj: Any = scraper.page
                page_obj.wait(3)
                html = page_obj.html
                ratios = self._parse_html(html)
            
            if ratios:
                result = {
                    "source": "myfxbook",
                    "ratios": ratios,
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                }
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
        # Jalankan proses scraping DrissionPage di thread terpisah
        result = await asyncio.to_thread(self.fetch_sync)

        # Simpan ke DB hanya jika ada ratios valid
        if "ratios" in result and result["ratios"]:
            cfg_key = "myfxbook_sentiment_latest"
            existing = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key)
            )).scalar_one_or_none()
            
            if existing:
                existing.value = json.dumps(result)
            else:
                self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))
            await self.session.commit()
        
        return result
