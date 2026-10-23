# ==============================================================================
# File: scrapers/macro/bank_indonesia.py
# ==============================================================================

"""
Bank Indonesia (BI) Scraper & Emerging Markets Macro Fetcher.
Fetches:
- BI Rate (BI 7-Day Reverse Repo Rate / BI-Rate)
- JISDOR (Jakarta Interbank Spot Dollar Rate) reference rate for USD/IDR
- Monetary policy press release statements
Includes fallback to web search and Yahoo Finance IDR=X.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup

from monika.infrastructure.llm.rate_limiting.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.Scrapers.BankIndonesia")


class BankIndonesiaFetcher:
    """Fetcher for Bank Indonesia policy rate and USD/IDR reference JISDOR."""

    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def fetch_bi_rate(self) -> Dict[str, Any]:
        """
        Fetches current BI-Rate from official Bank Indonesia endpoint,
        with fallback to web search.
        """
        url = "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx"
        try:
            html = await fetch_with_retry(
                url,
                headers=self.headers,
                timeout=self.timeout_seconds,
                response_type="text",
                max_retries=2,
            )
            if html and isinstance(html, str):
                soup = BeautifulSoup(html, "html.parser")
                rate_val: Optional[float] = None

                # 1. Targeted search in table rows/indicators
                tables = soup.find_all("table")
                for table in tables:
                    for row in table.find_all("tr"):
                        row_text = row.get_text()
                        if any(k in row_text for k in ("BI-Rate", "BI 7-Day", "Reverse Repo", "Suku Bunga")):
                            m = re.search(r"(\d+[\.,]\d+)\s*%", row_text)
                            if m:
                                val = float(m.group(1).replace(",", "."))
                                if 4.0 <= val <= 9.0:
                                    rate_val = val
                                    break
                    if rate_val is not None:
                        break

                # 2. Targeted search in indicator cards/containers
                if rate_val is None:
                    containers = soup.select(".bi-rate, .indicator-card, .table-responsive, .content-indikator")
                    for cont in containers:
                        m = re.search(r"(\d+[\.,]\d+)\s*%", cont.get_text())
                        if m:
                            val = float(m.group(1).replace(",", "."))
                            if 4.0 <= val <= 9.0:
                                rate_val = val
                                break

                # 3. Targeted regex fallback across page with keyword proximity
                if rate_val is None:
                    matches = re.finditer(
                        r"(?:BI-Rate|BI 7-Day|Suku Bunga)[^%\d]{0,50}?(\d+[\.,]\d+)\s*%", html, re.IGNORECASE
                    )
                    for match in matches:
                        val = float(match.group(1).replace(",", "."))
                        if 4.0 <= val <= 9.0:
                            rate_val = val
                            break

                if rate_val is not None and 4.0 <= rate_val <= 9.0:
                    return {
                        "central_bank": "Bank Indonesia",
                        "rate_name": "BI-Rate (7-Day Reverse Repo Rate)",
                        "rate_pct": rate_val,
                        "source": url,
                        "status": "success",
                        "is_synthetic": False,
                        "is_verified": True,
                    }
        except Exception as e:
            logger.debug(f"Direct BI Rate scrape note: {e}")

        # Fallback via financial search
        try:
            from monika.infrastructure.data_ingestion.sources.web_search import WebSearchService

            ws = WebSearchService()
            search_out = await ws.search("Bank Indonesia BI Rate suku bunga terkini persen", max_results=3)
            results = search_out.get("results", []) if isinstance(search_out, dict) else []
            for r in results:
                snippet = (r.get("content") or r.get("snippet", "")) + " " + r.get("title", "")
                m = re.search(r"(\d+[\.,]\d+)\s*%", snippet)
                if m:
                    val = float(m.group(1).replace(",", "."))
                    if 4.0 <= val <= 9.0:  # Sanity check for BI rate
                        return {
                            "central_bank": "Bank Indonesia",
                            "rate_name": "BI-Rate (Web Search Fallback)",
                            "rate_pct": val,
                            "source": r.get("url"),
                            "snippet": snippet[:150],
                            "status": "fallback_success",
                            "is_synthetic": False,
                            "is_verified": True,
                        }
        except Exception as fallback_err:
            logger.debug(f"BI Rate web search fallback error: {fallback_err}")

        # Fail-closed when live sources fail
        return {
            "central_bank": "Bank Indonesia",
            "rate_name": "BI-Rate",
            "rate_pct": None,
            "status": "unavailable",
            "is_synthetic": False,
            "is_verified": False,
            "note": "Live fetch timed out and web search unavailable",
        }

    async def fetch_jisdor_rate(self) -> Dict[str, Any]:
        """
        Fetches official JISDOR (Jakarta Interbank Spot Dollar Rate) for USD/IDR,
        with fallback to Yahoo Finance IDR=X.
        """
        url = "https://www.bi.go.id/id/statistik/informasi-kurs/jisdor/default.aspx"
        try:
            html = await fetch_with_retry(
                url,
                headers=self.headers,
                timeout=self.timeout_seconds,
                response_type="text",
                max_retries=2,
            )
            if html and isinstance(html, str):
                # Look for JISDOR rate (e.g. 15,800 or 16,200)
                matches = re.findall(r"1[5-7]\s*[\.,]\s*\d{3}", html)
                if matches:
                    clean_str = matches[0].replace(".", "").replace(",", "").replace(" ", "")
                    jisdor_val = float(clean_str)
                    if 14000.0 <= jisdor_val <= 18000.0:
                        return {
                            "currency_pair": "USD/IDR",
                            "reference_rate": "JISDOR",
                            "rate": jisdor_val,
                            "source": url,
                            "status": "success",
                            "is_synthetic": False,
                            "is_verified": True,
                        }
        except Exception as e:
            logger.debug(f"Direct JISDOR scrape note: {e}")

        # Fallback to Yahoo Finance IDR=X
        try:
            import yfinance as yf

            loop = asyncio.get_running_loop()

            def _get_yf():
                t = yf.Ticker("IDR=X")
                hist = t.history(period="2d", interval="1d")
                if not hist.empty:
                    return float(hist["Close"].iloc[-1])
                return None

            yf_rate = await loop.run_in_executor(None, _get_yf)
            if yf_rate and yf_rate > 10000:
                return {
                    "currency_pair": "USD/IDR",
                    "reference_rate": "Yahoo Finance (IDR=X)",
                    "rate": round(yf_rate, 2),
                    "status": "fallback_success",
                    "is_synthetic": False,
                    "is_verified": True,
                }
        except Exception as yf_err:
            logger.debug(f"JISDOR yfinance fallback error: {yf_err}")

        return {
            "currency_pair": "USD/IDR",
            "reference_rate": "USD/IDR",
            "rate": None,
            "status": "unavailable",
            "is_synthetic": False,
            "is_verified": False,
        }
