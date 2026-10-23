# ==============================================================================
# File: data_sources/sovereign_yield_spreads.py
# Monika Sovereign Bond Yield Spread & Macro Carry Engine
# ==============================================================================

"""
Sovereign 10-Year Government Bond Yield Spread Engine.

Extracts real-time and historical 10-year sovereign bond yields via Yahoo Finance
chart API with fail-closed fallback to verified database BondYieldData:
  - US 10Y vs Germany 10Y Bund (DE10Y)   -> EURUSD Fundamental Carry Driver
  - US 10Y vs UK 10Y Gilt (UK10Y)       -> GBPUSD Fundamental Carry Driver
  - US 10Y vs Japan 10Y JGB (JP10Y)      -> USDJPY Fundamental Carry Driver
  - US 10Y vs Australia 10Y (AU10Y)      -> AUDUSD Fundamental Carry Driver
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from monika.infrastructure.llm.rate_limiting.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.SovereignYieldSpreads")

DEFAULT_TIMEOUT: int = 6
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@dataclass(frozen=True, slots=True)
class YieldSpreadData:
    symbol_pair: str
    us_yield: float
    foreign_yield: float
    spread_bps: float
    spread_1d_change_bps: float
    macro_direction_bias: str  # "BULLISH_USD" | "BEARISH_USD" | "NEUTRAL"
    fundamental_signal: str  # e.g. "EURUSD_BEARISH" or "USDJPY_BULLISH"
    conviction: float  # 0.0 to 1.0


class SovereignYieldSpreads:
    """Calculates macro sovereign bond yield differentials for FX pairs."""

    YIELD_TICKERS = {
        "US_10Y": "^TNX",
        "GERMANY_10Y": "DE10YT=RR",
        "JAPAN_10Y": "JP10YT=RR",
        "UK_10Y": "GB10YT=RR",
        "AUSTRALIA_10Y": "AU10YT=RR",
    }

    @classmethod
    def _fetch_yahoo_chart_sync(cls, ticker: str) -> Optional[Tuple[float, float]]:
        """Returns (current_yield, previous_close_yield) via Yahoo Finance Chart API."""
        encoded_ticker = urllib.parse.quote(ticker)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?interval=1d&range=5d"
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    result = payload.get("chart", {}).get("result")
                    if result:
                        meta = result[0].get("meta", {})
                        curr_price = meta.get("regularMarketPrice")
                        prev_close = meta.get("chartPreviousClose", meta.get("previousClose", curr_price))
                        if curr_price is not None:
                            return float(curr_price), float(prev_close or curr_price)
        except urllib.error.HTTPError as e:
            try:
                e.close()
            except Exception:
                pass
            logger.debug(f"Failed fetching yield for {ticker}: {e}")
        except Exception as e:
            close_fn = getattr(e, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            logger.debug(f"Failed fetching yield for {ticker}: {e}")
        return None

    @classmethod
    async def _fetch_yahoo_chart_async(cls, ticker: str) -> Optional[Tuple[float, float]]:
        """Returns (current_yield, previous_close_yield) via Yahoo Finance Chart API using fetch_with_retry."""
        try:
            encoded_ticker = urllib.parse.quote(ticker)
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?interval=1d&range=5d"
            payload = await fetch_with_retry(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                response_type="json",
                timeout=DEFAULT_TIMEOUT,
            )
            if isinstance(payload, dict):
                result = payload.get("chart", {}).get("result")
                if result and isinstance(result, list) and len(result) > 0:
                    meta = result[0].get("meta", {})
                    curr_price = meta.get("regularMarketPrice")
                    prev_close = meta.get("chartPreviousClose", meta.get("previousClose", curr_price))
                    if curr_price is not None:
                        return float(curr_price), float(prev_close or curr_price)
        except Exception as e:
            logger.debug(f"Failed fetching async yield for {ticker}: {e}")
        return None

    @classmethod
    async def _fetch_db_fallback(
        cls, country_tenor: str, session: Optional[Any] = None
    ) -> Optional[Tuple[float, float]]:
        """Fetch latest (current_yield, previous_close_yield) from BondYieldData in database."""
        try:
            from sqlalchemy import select

            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.domain_models.market import BondYieldData, TreasuryYield

            alias_map = {
                "GERMANY_10Y": ["DE_10Y", "GERMANY_10Y"],
                "JAPAN_10Y": ["JP_10Y", "JAPAN_10Y"],
                "UK_10Y": ["UK_10Y", "GB_10Y", "GB10Y"],
                "AUSTRALIA_10Y": ["AU_10Y", "AUSTRALIA_10Y"],
                "US_10Y": ["US_10Y", "US10Y"],
            }
            db_candidates = list(dict.fromkeys([country_tenor] + alias_map.get(country_tenor, [])))

            async def _query(s):
                res = (
                    (
                        await s.execute(
                            select(BondYieldData.yield_percent)
                            .where(BondYieldData.country_tenor.in_(db_candidates))
                            .order_by(BondYieldData.date.desc())
                            .limit(2)
                        )
                    )
                    .scalars()
                    .all()
                )
                if res and len(res) >= 1:
                    curr = float(res[0])
                    prev = float(res[1]) if len(res) > 1 else curr
                    return curr, prev

                if country_tenor == "US_10Y":
                    ty_res = (
                        (
                            await s.execute(
                                select(TreasuryYield.yield_percent)
                                .where(TreasuryYield.tenor == "10Y")
                                .order_by(TreasuryYield.date.desc())
                                .limit(2)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if ty_res and len(ty_res) >= 1:
                        curr = float(ty_res[0])
                        prev = float(ty_res[1]) if len(ty_res) > 1 else curr
                        return curr, prev
                return None

            if session is not None:
                return await _query(session)
            async with get_session() as s:
                return await _query(s)
        except Exception as e:
            logger.debug(f"DB fallback failed for {country_tenor}: {e}")
            return None

    @classmethod
    def get_spreads_sync(cls) -> Dict[str, Any]:
        """
        Synchronous fallback calculating macro yield spreads.
        Fails closed if US 10Y data cannot be fetched.
        """
        us_ticker = cls.YIELD_TICKERS.get("US_10Y")
        us_data = cls._fetch_yahoo_chart_sync(us_ticker) if us_ticker else None
        if not us_data:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "us_10y_yield": None,
                "spreads": {},
                "status": "error",
                "error": "US 10Y yield data unavailable",
            }

        de_ticker = cls.YIELD_TICKERS.get("GERMANY_10Y")
        jp_ticker = cls.YIELD_TICKERS.get("JAPAN_10Y")
        uk_ticker = cls.YIELD_TICKERS.get("UK_10Y")
        au_ticker = cls.YIELD_TICKERS.get("AUSTRALIA_10Y")

        de_data = cls._fetch_yahoo_chart_sync(de_ticker) if de_ticker else None
        jp_data = cls._fetch_yahoo_chart_sync(jp_ticker) if jp_ticker else None
        uk_data = cls._fetch_yahoo_chart_sync(uk_ticker) if uk_ticker else None
        au_data = cls._fetch_yahoo_chart_sync(au_ticker) if au_ticker else None

        us_yield, us_prev = us_data
        spreads = {}

        if de_data:
            de_yield, de_prev = de_data
            us_de_curr_bps = (us_yield - de_yield) * 100.0
            us_de_prev_bps = (us_prev - de_prev) * 100.0
            delta_us_de = us_de_curr_bps - us_de_prev_bps
            eur_bias = (
                "EURUSD_BEARISH"
                if delta_us_de > 1.0
                else ("EURUSD_BULLISH" if delta_us_de < -1.0 else "EURUSD_NEUTRAL")
            )
            eur_conviction = min(0.9, float(abs(delta_us_de) / 10.0 + 0.5))
            spreads["EURUSD"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(de_yield, 3),
                "spread_bps": round(us_de_curr_bps, 1),
                "delta_1d_bps": round(delta_us_de, 1),
                "bias": eur_bias,
                "conviction": round(eur_conviction, 2),
            }

        if jp_data:
            jp_yield, jp_prev = jp_data
            us_jp_curr_bps = (us_yield - jp_yield) * 100.0
            us_jp_prev_bps = (us_prev - jp_prev) * 100.0
            delta_us_jp = us_jp_curr_bps - us_jp_prev_bps
            jpy_bias = (
                "USDJPY_BULLISH"
                if delta_us_jp > 1.0
                else ("USDJPY_BEARISH" if delta_us_jp < -1.0 else "USDJPY_NEUTRAL")
            )
            jpy_conviction = min(0.9, float(abs(delta_us_jp) / 10.0 + 0.5))
            spreads["USDJPY"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(jp_yield, 3),
                "spread_bps": round(us_jp_curr_bps, 1),
                "delta_1d_bps": round(delta_us_jp, 1),
                "bias": jpy_bias,
                "conviction": round(jpy_conviction, 2),
            }

        if uk_data:
            uk_yield, uk_prev = uk_data
            us_uk_curr_bps = (us_yield - uk_yield) * 100.0
            us_uk_prev_bps = (us_prev - uk_prev) * 100.0
            delta_us_uk = us_uk_curr_bps - us_uk_prev_bps
            gbp_bias = (
                "GBPUSD_BEARISH"
                if delta_us_uk > 1.0
                else ("GBPUSD_BULLISH" if delta_us_uk < -1.0 else "GBPUSD_NEUTRAL")
            )
            gbp_conviction = min(0.9, float(abs(delta_us_uk) / 10.0 + 0.5))
            spreads["GBPUSD"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(uk_yield, 3),
                "spread_bps": round(us_uk_curr_bps, 1),
                "delta_1d_bps": round(delta_us_uk, 1),
                "bias": gbp_bias,
                "conviction": round(gbp_conviction, 2),
            }

        if au_data:
            au_yield, au_prev = au_data
            us_au_curr_bps = (us_yield - au_yield) * 100.0
            us_au_prev_bps = (us_prev - au_prev) * 100.0
            delta_us_au = us_au_curr_bps - us_au_prev_bps
            aud_bias = (
                "AUDUSD_BEARISH"
                if delta_us_au > 1.0
                else ("AUDUSD_BULLISH" if delta_us_au < -1.0 else "AUDUSD_NEUTRAL")
            )
            aud_conviction = min(0.9, float(abs(delta_us_au) / 10.0 + 0.5))
            spreads["AUDUSD"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(au_yield, 3),
                "spread_bps": round(us_au_curr_bps, 1),
                "delta_1d_bps": round(delta_us_au, 1),
                "bias": aud_bias,
                "conviction": round(aud_conviction, 2),
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "us_10y_yield": round(us_yield, 3),
            "spreads": spreads,
        }

    @classmethod
    async def get_spreads(cls, session: Optional[Any] = None) -> Dict[str, Any]:
        """
        Asynchronously calculates macro yield spreads across core FX pairs.
        Uses Yahoo Finance async API as primary, falling back to verified BondYieldData in database.
        Fails closed without fabricating numbers if data is unavailable.
        """

        async def _get_yield_pair(ticker_key: str, country_tenor: str) -> Optional[Tuple[float, float]]:
            ticker = cls.YIELD_TICKERS.get(ticker_key)
            if ticker:
                res = await cls._fetch_yahoo_chart_async(ticker)
                if res is not None:
                    return res
            # Failover to verified database storage
            return await cls._fetch_db_fallback(country_tenor, session)

        us_data = await _get_yield_pair("US_10Y", "US_10Y")
        if not us_data:
            logger.warning("SovereignYieldSpreads: US 10Y yield unavailable (fail-closed)")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "us_10y_yield": None,
                "spreads": {},
                "status": "error",
                "error": "US 10Y yield data unavailable",
            }

        us_yield, us_prev = us_data
        spreads: Dict[str, Any] = {}

        # 1. EURUSD (US 10Y vs German 10Y Bund)
        de_data = await _get_yield_pair("GERMANY_10Y", "DE_10Y")
        if de_data:
            de_yield, de_prev = de_data
            us_de_curr_bps = (us_yield - de_yield) * 100.0
            us_de_prev_bps = (us_prev - de_prev) * 100.0
            delta_us_de = us_de_curr_bps - us_de_prev_bps
            eur_bias = (
                "EURUSD_BEARISH"
                if delta_us_de > 1.0
                else ("EURUSD_BULLISH" if delta_us_de < -1.0 else "EURUSD_NEUTRAL")
            )
            eur_conviction = min(0.9, float(abs(delta_us_de) / 10.0 + 0.5))
            spreads["EURUSD"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(de_yield, 3),
                "spread_bps": round(us_de_curr_bps, 1),
                "delta_1d_bps": round(delta_us_de, 1),
                "bias": eur_bias,
                "conviction": round(eur_conviction, 2),
            }

        # 2. USDJPY (US 10Y vs Japan 10Y JGB)
        jp_data = await _get_yield_pair("JAPAN_10Y", "JP_10Y")
        if jp_data:
            jp_yield, jp_prev = jp_data
            us_jp_curr_bps = (us_yield - jp_yield) * 100.0
            us_jp_prev_bps = (us_prev - jp_prev) * 100.0
            delta_us_jp = us_jp_curr_bps - us_jp_prev_bps
            jpy_bias = (
                "USDJPY_BULLISH"
                if delta_us_jp > 1.0
                else ("USDJPY_BEARISH" if delta_us_jp < -1.0 else "USDJPY_NEUTRAL")
            )
            jpy_conviction = min(0.9, float(abs(delta_us_jp) / 10.0 + 0.5))
            spreads["USDJPY"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(jp_yield, 3),
                "spread_bps": round(us_jp_curr_bps, 1),
                "delta_1d_bps": round(delta_us_jp, 1),
                "bias": jpy_bias,
                "conviction": round(jpy_conviction, 2),
            }

        # 3. GBPUSD (US 10Y vs UK 10Y Gilt)
        uk_data = await _get_yield_pair("UK_10Y", "UK_10Y")
        if uk_data:
            uk_yield, uk_prev = uk_data
            us_uk_curr_bps = (us_yield - uk_yield) * 100.0
            us_uk_prev_bps = (us_prev - uk_prev) * 100.0
            delta_us_uk = us_uk_curr_bps - us_uk_prev_bps
            gbp_bias = (
                "GBPUSD_BEARISH"
                if delta_us_uk > 1.0
                else ("GBPUSD_BULLISH" if delta_us_uk < -1.0 else "GBPUSD_NEUTRAL")
            )
            gbp_conviction = min(0.9, float(abs(delta_us_uk) / 10.0 + 0.5))
            spreads["GBPUSD"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(uk_yield, 3),
                "spread_bps": round(us_uk_curr_bps, 1),
                "delta_1d_bps": round(delta_us_uk, 1),
                "bias": gbp_bias,
                "conviction": round(gbp_conviction, 2),
            }

        # 4. AUDUSD (US 10Y vs Australia 10Y)
        au_data = await _get_yield_pair("AUSTRALIA_10Y", "AU_10Y")
        if au_data:
            au_yield, au_prev = au_data
            us_au_curr_bps = (us_yield - au_yield) * 100.0
            us_au_prev_bps = (us_prev - au_prev) * 100.0
            delta_us_au = us_au_curr_bps - us_au_prev_bps
            aud_bias = (
                "AUDUSD_BEARISH"
                if delta_us_au > 1.0
                else ("AUDUSD_BULLISH" if delta_us_au < -1.0 else "AUDUSD_NEUTRAL")
            )
            aud_conviction = min(0.9, float(abs(delta_us_au) / 10.0 + 0.5))
            spreads["AUDUSD"] = {
                "us_yield": round(us_yield, 3),
                "foreign_yield": round(au_yield, 3),
                "spread_bps": round(us_au_curr_bps, 1),
                "delta_1d_bps": round(delta_us_au, 1),
                "bias": aud_bias,
                "conviction": round(aud_conviction, 2),
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "us_10y_yield": round(us_yield, 3),
            "spreads": spreads,
        }
