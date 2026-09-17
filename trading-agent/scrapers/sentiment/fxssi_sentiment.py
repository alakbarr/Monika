# ==============================================================================
# File: scrapers/sentiment/fxssi_sentiment.py
# ==============================================================================

"""
FXSSI Current Ratio — Data posisi trader ritel untuk aset seperti XTIUSD.
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

logger = logging.getLogger("TradingAgent.FXSSISentiment")

SYMBOL_ALIASES = {
    "EURUSD": ["EURUSD", "EUR/USD", "EUR / USD"],
    "GBPUSD": ["GBPUSD", "GBP/USD", "GBP / USD"],
    "USDJPY": ["USDJPY", "USD/JPY", "USD / JPY"],
    "AUDUSD": ["AUDUSD", "AUD/USD", "AUD / USD"],
    "XAUUSD": ["XAUUSD", "XAU/USD", "GOLD"],
    "XTIUSD": ["XTIUSD", "WTI", "OIL", "US OIL", "CRUDE OIL", "WTICRUDE"],
    "BTCUSD": ["BTCUSD", "BTC/USD", "BITCOIN"],
}


class FXSSISentimentFetcher:
    def __init__(self, session: AsyncSession, headless=True):
        self.headless = headless
        self.session = session
        self.url = "https://fxssi.com/tools/current-ratio"
        self.symbols = list(SYMBOL_ALIASES.keys())
        
    def _parse_html(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        results = {}
        
        # 1. Parse dari elemen DOM kartu pair FXSSI (.cur-rat-cur-pair atau .sentiment-ratios)
        pair_cards = soup.select(".cur-rat-cur-pair, .cur-rat-pair, [data-filter]")
        for card in pair_cards:
            filter_attr = card.get("data-filter")
            filter_raw = " ".join(filter_attr) if isinstance(filter_attr, list) else (filter_attr or card.get_text())
            filter_val = filter_raw.upper().replace("/", "").replace(" ", "")
            matched_sym = None
            for standard_sym, aliases in SYMBOL_ALIASES.items():
                if any(alias.replace("/", "").replace(" ", "").upper() in filter_val for alias in aliases):
                    matched_sym = standard_sym
                    break
            
            if matched_sym and matched_sym not in results:
                # Cari baris Average atau broker bar
                avg_broker = card.select_one(".broker-average, .cur-rat-broker[data-name='Average'], .average-line, .cur-rat-broker")
                target_ele = avg_broker if avg_broker else card
                
                left_bar = target_ele.select_one(".ratio-bar-left")
                right_bar = target_ele.select_one(".ratio-bar-right")
                if left_bar and right_bar:
                    left_text = re.search(r"(\d+(?:\.\d+)?)", left_bar.get_text() or "")
                    right_text = re.search(r"(\d+(?:\.\d+)?)", right_bar.get_text() or "")
                    if left_text and right_text:
                        long_val = float(left_text.group(1))
                        short_val = float(right_text.group(1))
                        results[matched_sym] = {
                            "long_percent": long_val,
                            "short_percent": short_val,
                            "long_short_ratio": round(long_val / max(short_val, 0.1), 4)
                        }

        # 2. Fallback text regex
        text = soup.get_text(separator=" ", strip=True)
        for standard_sym, aliases in SYMBOL_ALIASES.items():
            if standard_sym in results:
                continue
            for alias in aliases:
                match = re.search(rf"{re.escape(alias)}(?:(?!Buy Sell).)*?Average\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%", text, re.IGNORECASE)
                if match:
                    long_pct = float(match.group(1))
                    short_pct = float(match.group(2))
                    results[standard_sym] = {
                        "long_percent": long_pct,
                        "short_percent": short_pct,
                        "long_short_ratio": round(long_pct / max(short_pct, 0.1), 4)
                    }
                    break
                
                fallback_match = re.search(rf"{re.escape(alias)}(?:(?!Buy Sell).)*?(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%", text, re.IGNORECASE)
                if fallback_match:
                    results[standard_sym] = {
                        "long_percent": float(fallback_match.group(1)),
                        "short_percent": float(fallback_match.group(2)),
                        "long_short_ratio": round(float(fallback_match.group(1)) / max(float(fallback_match.group(2)), 0.1), 4)
                    }
                    break

        return results

    def fetch_sync(self) -> dict:
        scraper = BaseScraper(headless=self.headless, profile_name="fxssi")
        result = {"error": "Failed to extract FXSSI data"}
        ratios = {}
        
        try:
            logger.info("Fetching FXSSI Sentiment via DrissionPage BaseScraper...")
            
            success = scraper.navigate_with_fallback(
                self.url,
                wait_selector="css:.cur-rat-container, .sentiment-ratios, .cur-rat-pairs, #last-update"
            )
            if success and scraper.page:
                # Tunggu data dimuat
                page_obj: Any = scraper.page
                page_obj.wait(3)
                html = page_obj.html
                ratios = self._parse_html(html)
            
            if ratios:
                result = {
                    "source": "fxssi",
                    "ratios": ratios,
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                }
            else:
                result = {"error": "FXSSI returned empty or failed to parse."}
                logger.warning("FXSSI Sentiment returned empty or failed to parse.")
                
        except Exception as e:
            logger.warning(f"Error fetching FXSSI Sentiment: {e}")
            result = {"error": str(e)}
        finally:
            scraper.close()
            
        return result

    async def fetch(self) -> dict:
        # Jalankan proses scraping DrissionPage di thread terpisah
        result = await asyncio.to_thread(self.fetch_sync)

        # 1. Simpan snapshot terbaru ke DB hanya jika ada ratios valid
        if "ratios" in result and result["ratios"]:
            cfg_key = "fxssi_sentiment_latest"
            existing = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key)
            )).scalar_one_or_none()
            
            if existing:
                existing.value = json.dumps(result)
            else:
                self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))

        # 2. Simpan atau append ke time-series history snapshot jika data valid
        if "ratios" in result and result["ratios"]:
            hist_key = "fxssi_sentiment_history"
            hist_row = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == hist_key)
            )).scalar_one_or_none()

            history_list = []
            if hist_row and hist_row.value:
                try:
                    history_list = json.loads(hist_row.value)
                    if not isinstance(history_list, list):
                        history_list = []
                except Exception:
                    history_list = []

            history_list.append({
                "timestamp": result.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
                "ratios": result["ratios"]
            })
            # Retain up to 360 recent snapshots (approx 180-360 days)
            if len(history_list) > 360:
                history_list = history_list[-360:]

            if hist_row:
                hist_row.value = json.dumps(history_list)
            else:
                self.session.add(SystemConfig(key=hist_key, value=json.dumps(history_list)))

        await self.session.commit()
        return result
