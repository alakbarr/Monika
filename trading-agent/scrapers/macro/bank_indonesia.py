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
from typing import Dict, Any, Optional
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger("TradingAgent.Scrapers.BankIndonesia")


class BankIndonesiaFetcher:
    """Fetcher for Bank Indonesia policy rate and USD/IDR reference JISDOR."""

    def __init__(self, timeout_seconds: int = 15):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
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
            async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        html = await resp.text(errors="replace")
                        soup = BeautifulSoup(html, "html.parser")
                        # Look for percentage pattern near BI-Rate
                        text = soup.get_text()
                        match = re.search(r"(\d+[\.,]\d+)\s*%", text)
                        if match:
                            rate_val = float(match.group(1).replace(",", "."))
                            return {
                                "central_bank": "Bank Indonesia",
                                "rate_name": "BI-Rate (7-Day Reverse Repo Rate)",
                                "rate_pct": rate_val,
                                "source": url,
                                "status": "success",
                            }
        except Exception as e:
            logger.debug(f"Direct BI Rate scrape note: {e}")

        # Fallback via financial search
        try:
            from data_sources.web_search import WebSearch
            ws = WebSearch()
            results = await ws.search("Bank Indonesia BI Rate suku bunga terkini persen", num_results=3)
            for r in results:
                snippet = r.get("snippet", "") + " " + r.get("title", "")
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
                        }
        except Exception as fallback_err:
            logger.debug(f"BI Rate web search fallback error: {fallback_err}")

        # Baseline default based on latest known BI regime (6.00% - 6.25%)
        return {
            "central_bank": "Bank Indonesia",
            "rate_name": "BI-Rate",
            "rate_pct": 6.00,
            "status": "estimated_baseline",
            "note": "Live fetch timed out, returned baseline policy rate",
        }

    async def fetch_jisdor_rate(self) -> Dict[str, Any]:
        """
        Fetches official JISDOR (Jakarta Interbank Spot Dollar Rate) for USD/IDR,
        with fallback to Yahoo Finance IDR=X.
        """
        url = "https://www.bi.go.id/id/statistik/informasi-kurs/jisdor/default.aspx"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        html = await resp.text(errors="replace")
                        # Look for JISDOR rate (e.g. 15,800 or 16,200)
                        matches = re.findall(r"1[5-7]\s*[\.,]\s*\d{3}", html)
                        if matches:
                            clean_str = matches[0].replace(".", "").replace(",", "").replace(" ", "")
                            jisdor_val = float(clean_str)
                            return {
                                "currency_pair": "USD/IDR",
                                "reference_rate": "JISDOR",
                                "rate": jisdor_val,
                                "source": url,
                                "status": "success",
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
                }
        except Exception as yf_err:
            logger.debug(f"JISDOR yfinance fallback error: {yf_err}")

        return {
            "currency_pair": "USD/IDR",
            "reference_rate": "USD/IDR Baseline",
            "rate": 16250.0,
            "status": "estimated_baseline",
        }
