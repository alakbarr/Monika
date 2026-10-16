# ==============================================================================
# File: scrapers/sentiment/fxssi_sentiment.py
# ==============================================================================

"""
FXSSI Current Ratio — Data posisi trader ritel untuk aset seperti XTIUSD.
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

from monika.infrastructure.data_ingestion.scrapers.base_scraper import BaseScraper
from monika.infrastructure.database.models import SystemConfig

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
                avg_broker = card.select_one(
                    ".broker-average, .cur-rat-broker[data-name='Average'], .average-line, .cur-rat-broker"
                )
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
                            "long_short_ratio": round(long_val / max(short_val, 0.1), 4),
                        }

        # 2. Fallback text regex
        text = soup.get_text(separator=" ", strip=True)
        for standard_sym, aliases in SYMBOL_ALIASES.items():
            if standard_sym in results:
                continue
            for alias in aliases:
                match = re.search(
                    rf"{re.escape(alias)}(?:(?!Buy Sell).)*?Average\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%",
                    text,
                    re.IGNORECASE,
                )
                if match:
                    long_pct = float(match.group(1))
                    short_pct = float(match.group(2))
                    results[standard_sym] = {
                        "long_percent": long_pct,
                        "short_percent": short_pct,
                        "long_short_ratio": round(long_pct / max(short_pct, 0.1), 4),
                    }
                    break

                fallback_match = re.search(
                    rf"{re.escape(alias)}(?:(?!Buy Sell).)*?(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%", text, re.IGNORECASE
                )
                if fallback_match:
                    results[standard_sym] = {
                        "long_percent": float(fallback_match.group(1)),
                        "short_percent": float(fallback_match.group(2)),
                        "long_short_ratio": round(
                            float(fallback_match.group(1)) / max(float(fallback_match.group(2)), 0.1), 4
                        ),
                    }
                    break

        return results

    def _fetch_via_http(self) -> dict:
        """Pengambilan cepat HTML SSR langsung via HTTP GET tanpa overhead browser."""
        import urllib.request

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(self.url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            status = getattr(resp, "status", getattr(resp, "code", 200))
            if status != 200:
                raise RuntimeError(f"HTTP GET returned status {status}")
            html_text = resp.read().decode("utf-8", errors="replace")
            return self._parse_html(html_text)

    def fetch_sync(self) -> dict:
        import time

        # 1. Coba jalur cepat HTTP langsung (SSR HTML)
        t0 = time.monotonic()
        try:
            ratios = self._fetch_via_http()
            if ratios and len(ratios) >= 3:
                elapsed = time.monotonic() - t0
                logger.info(f"Fetched FXSSI Sentiment via direct HTTP in {elapsed:.2f}s ({len(ratios)} pairs).")
                return {
                    "source": "fxssi",
                    "ratios": ratios,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as http_err:
            logger.debug(f"Direct HTTP fetch for FXSSI unviable ({http_err}); falling back to browser.")

        # 2. Fallback browser DrissionPage dengan mode eager & no_imgs
        scraper = None
        try:
            logger.info("Fetching FXSSI Sentiment via browser fallback (load_mode=eager)...")
            scraper = BaseScraper(headless=self.headless, profile_name="fxssi", load_mode="eager", no_imgs=True)

            scraper.navigate_with_fallback(
                self.url,
                wait_selector="css:.cur-rat-container, .sentiment-ratios, .cur-rat-pairs, #last-update",
                timeout=20,
            )
            ratios = {}
            if scraper.page:
                page_obj: Any = scraper.page
                try:
                    page_obj.wait(1.5)
                except Exception:
                    pass
                html = getattr(page_obj, "html", "") or ""
                if html:
                    ratios = self._parse_html(html)

            if ratios:
                return {
                    "source": "fxssi",
                    "ratios": ratios,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                logger.warning("FXSSI Sentiment returned empty or failed to parse.")
                return {"error": "FXSSI returned empty or failed to parse."}

        except Exception as e:
            logger.warning(f"Error fetching FXSSI Sentiment: {e}")
            return {"error": str(e)}
        finally:
            if scraper is not None:
                scraper.close()

    async def fetch(self) -> dict:
        # Jalankan proses scraping DrissionPage di thread terpisah
        result = await asyncio.to_thread(self.fetch_sync)

        # Simpan snapshot terbaru dan time-series history ke DB jika ratios valid
        if self.session and "ratios" in result and result.get("ratios"):
            cfg_key = "fxssi_sentiment_latest"
            hist_key = "fxssi_sentiment_history"

            # Query both rows in read phase before mutating any session state to eliminate mid-query autoflush
            existing = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))
            ).scalar_one_or_none()

            hist_row = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == hist_key))
            ).scalar_one_or_none()

            # 1. Simpan snapshot terbaru
            if existing:
                existing.value = json.dumps(result)
            else:
                self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))

            # 2. Simpan atau append ke time-series history snapshot
            history_list = []
            if hist_row and hist_row.value:
                try:
                    history_list = json.loads(hist_row.value)
                    if not isinstance(history_list, list):
                        history_list = []
                except Exception:
                    history_list = []

            history_list.append(
                {
                    "timestamp": result.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
                    "ratios": result["ratios"],
                }
            )
            # Retain up to 360 recent snapshots (approx 180-360 days)
            if len(history_list) > 360:
                history_list = history_list[-360:]

            if hist_row:
                hist_row.value = json.dumps(history_list)
            else:
                self.session.add(SystemConfig(key=hist_key, value=json.dumps(history_list)))

            await self.session.commit()

        return result
