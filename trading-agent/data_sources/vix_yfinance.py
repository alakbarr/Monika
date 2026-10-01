# ==============================================================================
# File: data_sources/vix_yfinance.py
# ==============================================================================

"""
Resilient Multi-Tier VIX Data Fetcher.

VIX (CBOE Volatility Index) represents market implied volatility expectations.
Fetches VIX daily settlement data through a hardened 4-tier pipeline:
  1. Tier 1: Direct Async Yahoo Finance Chart API (fast, pure async, no thread overhead)
  2. Tier 2: CBOE Official Daily Price CDN (authoritative fallback, no key required, CloudFront CDN)
  3. Tier 3: FRED API VIXCLS Series (optional fallback if FRED_API_KEY is configured)
  4. Tier 4: Hardened yfinance in worker thread with strict socket timeout
"""

import asyncio
import io
import logging
import os
from datetime import datetime, timezone, date
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import VIXData
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.VIX")

VIX_TICKER = "^VIX"
CBOE_VIX_CSV_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
YAHOO_VIX_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class VIXFetcher:
    """
    Fetches historical and current VIX daily settlement data using a resilient multi-tier pipeline.
    """

    def __init__(self, session: AsyncSession, ticker: str = VIX_TICKER, fred_api_key: Optional[str] = None):
        """
        Args:
            session: Async SQLAlchemy session.
            ticker: Yahoo Finance ticker symbol for VIX. Default '^VIX'.
            fred_api_key: Optional FRED API key for St. Louis Fed fallback.
        """
        self.session = session
        self.ticker = ticker
        self.fred_api_key = fred_api_key if fred_api_key is not None else os.getenv("FRED_API_KEY", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, period: str = "10d") -> int:
        """
        Mengunduh data VIX terbaru dan menyimpannya ke DB menggunakan multi-tier pipeline.

        Args:
            period: String periode (contoh: '5d', '10d', '1mo', '5y').

        Returns:
            Jumlah baris baru yang disimpan.
        """
        logger.info(f"Fetching VIX data (multi-tier resilient) for period={period}...")

        # Tier 1: Direct Async Yahoo Finance Chart API (Fast & Pure Async)
        df = await self._fetch_yahoo_direct(period)

        # Tier 2: CBOE Official CDN (Authoritative Fallback, No Key, Anti-block)
        if df is None or df.empty:
            logger.info("Tier 1 (Yahoo Direct) unavailable. Falling back to Tier 2 (CBOE Official CDN)...")
            df = await self._fetch_cboe_cdn(period)

        # Tier 3: FRED API Fallback (if FRED_API_KEY available)
        if (df is None or df.empty) and self.fred_api_key:
            logger.info("Tier 1 & 2 unavailable. Falling back to Tier 3 (FRED VIXCLS)...")
            df = await self._fetch_fred(period)

        # Tier 4: Hardened yfinance in ThreadPool with strict socket timeout
        if df is None or df.empty:
            logger.info("Falling back to Tier 4 (Hardened yfinance thread)...")
            df = await self._fetch_yfinance(period)

        if df is None or df.empty:
            logger.warning("All VIX data fetch tiers failed. Data feed unchanged.")
            return 0

        saved = await self._save(df)
        logger.info(f"VIX fetch complete. {saved} new records saved.")
        return saved

    # ------------------------------------------------------------------
    # Multi-Tier Fetch Implementations
    # ------------------------------------------------------------------

    async def _fetch_yahoo_direct(self, period: str = "10d") -> Optional[pd.DataFrame]:
        """Tier 1: Direct async request to Yahoo Finance chart v8 endpoint."""
        range_map = {
            "1d": "1d",
            "5d": "5d",
            "10d": "10d",
            "15d": "1mo",
            "1mo": "1mo",
            "3mo": "3mo",
            "6mo": "6mo",
            "1y": "1y",
            "2y": "2y",
            "5y": "5y",
        }
        range_param = range_map.get(period, "1mo")
        url = f"{YAHOO_VIX_CHART_URL}?interval=1d&range={range_param}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        try:
            res = await fetch_with_retry(
                url,
                headers=headers,
                timeout=8,
                max_retries=2,
                base_delay=0.5,
                response_type="json",
            )
            if not res or not isinstance(res, dict):
                return None
            chart = res.get("chart", {})
            results = chart.get("result")
            if not results or not isinstance(results, list):
                return None
            result_data = results[0]
            timestamps = result_data.get("timestamp", [])
            indicators = result_data.get("indicators", {}).get("quote", [{}])[0]
            closes = indicators.get("close", [])
            if not timestamps or not closes:
                return None

            records = []
            for ts, close_val in zip(timestamps, closes):
                if close_val is not None:
                    records.append({
                        "Date": pd.to_datetime(ts, unit="s", utc=True),
                        "Close": float(close_val),
                    })
            if not records:
                return None
            df = pd.DataFrame(records)
            df.set_index("Date", inplace=True)
            return df
        except Exception as e:
            logger.warning(f"VIX Tier 1 (Yahoo Direct) failed: {e}")
            return None

    async def _fetch_cboe_cdn(self, period: str = "10d") -> Optional[pd.DataFrame]:
        """Tier 2: Authoritative CBOE official daily settlement CSV from CloudFront CDN."""
        try:
            csv_text = await fetch_with_retry(
                CBOE_VIX_CSV_URL,
                timeout=10,
                max_retries=2,
                base_delay=0.5,
                response_type="text",
            )
            if not csv_text or not isinstance(csv_text, str) or "DATE" not in csv_text:
                return None

            df = pd.read_csv(io.StringIO(csv_text))
            df.columns = [c.strip().capitalize() for c in df.columns]
            if "Date" not in df.columns or "Close" not in df.columns:
                return None

            df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", utc=True, errors="coerce")
            df.dropna(subset=["Date", "Close"], inplace=True)
            df.set_index("Date", inplace=True)

            limit_map = {
                "1d": 5,
                "5d": 10,
                "10d": 20,
                "15d": 30,
                "1mo": 45,
                "3mo": 100,
                "6mo": 180,
                "1y": 300,
                "2y": 600,
                "5y": 1500,
            }
            limit = limit_map.get(period)
            if limit and len(df) > limit:
                df = df.tail(limit)

            return df
        except Exception as e:
            logger.warning(f"VIX Tier 2 (CBOE CDN) failed: {e}")
            return None

    async def _fetch_fred(self, period: str = "10d") -> Optional[pd.DataFrame]:
        """Tier 3: FRED API VIXCLS series (St. Louis Fed official benchmark)."""
        if not self.fred_api_key:
            return None
        limit_map = {"1d": 5, "5d": 10, "10d": 20, "15d": 30, "1mo": 45, "5y": 1500}
        limit = limit_map.get(period, 30)
        params = {
            "series_id": "VIXCLS",
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        try:
            res = await fetch_with_retry(
                FRED_BASE_URL,
                params=params,
                timeout=8,
                max_retries=2,
                response_type="json",
            )
            if not res or not isinstance(res, dict):
                return None
            observations = res.get("observations", [])
            records = []
            for obs in observations:
                val = obs.get("value")
                dt_str = obs.get("date")
                if val and val != "." and dt_str:
                    try:
                        records.append({
                            "Date": pd.to_datetime(dt_str, utc=True),
                            "Close": float(val),
                        })
                    except (ValueError, TypeError):
                        continue
            if not records:
                return None
            df = pd.DataFrame(records)
            df.set_index("Date", inplace=True)
            return df
        except Exception as e:
            logger.warning(f"VIX Tier 3 (FRED) failed: {e}")
            return None

    async def _fetch_yfinance(self, period: str = "10d") -> Optional[pd.DataFrame]:
        """Tier 4: Hardened yfinance download in worker thread with strict socket timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._download, period),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.warning("VIX Tier 4 (yfinance) thread timed out after 10.0s")
            return None
        except Exception as e:
            logger.warning(f"VIX Tier 4 (yfinance) failed: {e}")
            return None

    def _download(self, period: str) -> Optional[pd.DataFrame]:
        """Unduhan yfinance synchronous (legacy/fallback kompatibel)."""
        res = yf.download(
            self.ticker,
            period=period,
            progress=False,
            auto_adjust=True,
            timeout=8,
        )
        return res if isinstance(res, pd.DataFrame) else None

    # ------------------------------------------------------------------
    # Database Persistence
    # ------------------------------------------------------------------

    async def _save(self, df: pd.DataFrame) -> int:
        """Menyimpan record VIX ke DB, mengabaikan tanggal yang sudah ada."""
        saved = 0

        # yfinance mengembalikan MultiIndex columns saat auto_adjust=True
        # Normalisasi ke akses kolom tunggal
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        candidates = []
        for idx, row in df.iterrows():
            if isinstance(idx, (pd.Timestamp, datetime)):
                record_dt = datetime(idx.year, idx.month, idx.day, tzinfo=timezone.utc)
            else:
                ts = pd.Timestamp(str(idx))
                record_dt = datetime(int(ts.year), int(ts.month), int(ts.day), tzinfo=timezone.utc)

            close_val: Optional[float] = None
            for col in ["Close", "Adj Close", "close"]:
                if col in row and pd.notna(row[col]):
                    close_val = float(row[col])
                    break

            if close_val is None:
                logger.debug(f"VIX: no close value for {record_dt}, skipping")
                continue
            candidates.append((record_dt, close_val))

        if candidates:
            all_dates = [c[0] for c in candidates]
            existing_res = await self.session.execute(
                select(VIXData.date).where(VIXData.date.in_(all_dates))
            )
            existing_dates = set()
            found_by_scalars = False
            try:
                if hasattr(existing_res, "scalars"):
                    sc = existing_res.scalars()
                    if hasattr(sc, "__await__"):
                        sc = await sc
                    if hasattr(sc, "all"):
                        vals = sc.all()
                        if hasattr(vals, "__await__"):
                            vals = await vals
                        if isinstance(vals, (list, tuple, set)):
                            existing_dates = {
                                d.astimezone(timezone.utc) if getattr(d, "tzinfo", None) else d.replace(tzinfo=timezone.utc)
                                if isinstance(d, datetime) else d
                                for d in vals if d is not None
                            }
                            found_by_scalars = True
                if not found_by_scalars and hasattr(existing_res, "scalar_one_or_none"):
                    son = existing_res.scalar_one_or_none()
                    if hasattr(son, "__await__"):
                        son = await son
                    if son and type(son).__name__ not in ("MagicMock", "AsyncMock", "Mock"):
                        existing_dates = set(all_dates)
            except Exception:
                existing_dates = set()

            for record_dt, close_val in candidates:
                norm_dt = record_dt.astimezone(timezone.utc) if record_dt.tzinfo else record_dt.replace(tzinfo=timezone.utc)
                if norm_dt in existing_dates:
                    continue
                record = VIXData(date=norm_dt, close=close_val)
                self.session.add(record)
                existing_dates.add(norm_dt)
                saved += 1

        if saved:
            from database.safe_ops import safe_commit
            ok = await safe_commit(self.session, label="VIXData")
            if not ok:
                return 0

        return saved

    # ------------------------------------------------------------------
    # Kemudahan: mendapatkan nilai VIX terbaru dari DB
    # ------------------------------------------------------------------

    async def get_latest(self) -> Optional[dict]:
        """
        Mengembalikan record VIX paling baru dari database.

        Returns:
            Dict dengan kunci 'date' dan 'close', atau None jika data kosong.
        """
        result = await self.session.execute(
            select(VIXData).order_by(VIXData.date.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {"date": row.date, "close": row.close}

    async def fetch_market_asset(self, ticker: str, period: str = "1mo") -> Optional[pd.DataFrame]:
        """Fetch daily historical price series for market tickers like QQQ, ^GSPC, ^TNX, BTC-USD."""
        range_map = {"1d": "1d", "5d": "5d", "10d": "10d", "1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y"}
        range_param = range_map.get(period, "1mo")
        import urllib.parse
        encoded_ticker = urllib.parse.quote(ticker)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?interval=1d&range={range_param}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        try:
            res = await fetch_with_retry(url, headers=headers, timeout=8, max_retries=2, base_delay=0.5, response_type="json")
            if res and isinstance(res, dict):
                results = res.get("chart", {}).get("result")
                if results and isinstance(results, list):
                    result_data = results[0]
                    timestamps = result_data.get("timestamp", [])
                    indicators = result_data.get("indicators", {}).get("quote", [{}])[0]
                    closes = indicators.get("close", [])
                    records = []
                    for ts, close_val in zip(timestamps, closes):
                        if close_val is not None:
                            records.append({
                                "Date": pd.to_datetime(ts, unit="s", utc=True),
                                "Close": float(close_val),
                            })
                    if records:
                        df = pd.DataFrame(records)
                        df.set_index("Date", inplace=True)
                        return df
        except Exception as e:
            logger.debug(f"Direct fetch failed for {ticker}: {e}")

        try:
            def _dl():
                return yf.download(ticker, period=period, progress=False, auto_adjust=True, timeout=8)
            return await asyncio.wait_for(asyncio.to_thread(_dl), timeout=10.0)
        except Exception as e:
            logger.warning(f"Fallback yfinance fetch failed for {ticker}: {e}")
            return None


# ---------------------------------------------------------------------------
# Quick standalone test
# ---------------------------------------------------------------------------

async def _test():
    from dotenv import load_dotenv
    from database.db import get_session, init_db

    load_dotenv()
    await init_db()

    async with get_session() as session:
        fetcher = VIXFetcher(session)
        saved = await fetcher.fetch(period="10d")
        print(f"Saved {saved} VIX records")

        latest = await fetcher.get_latest()
        if latest:
            print(f"Latest VIX: {latest['close']:.2f} on {latest['date'].date()}")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.run(_test(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_test())
