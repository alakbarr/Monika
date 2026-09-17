# ==============================================================================
# File: data_sources/vix_yfinance.py
# ==============================================================================

"""
Async VIX Data Fetcher using yfinance.

VIX (CBOE Volatility Index) represents market implied volatility expectations.
Data source: Yahoo Finance via yfinance (public endpoint).

Note: yfinance executes synchronously; blocking network calls are dispatched
via asyncio executor threads to prevent blocking the async event loop.
"""

import asyncio
import logging
from datetime import datetime, timezone, date
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import VIXData

logger = logging.getLogger("TradingAgent.VIX")

VIX_TICKER = "^VIX"


class VIXFetcher:
    """
    Fetches historical and current VIX daily settlement data from Yahoo Finance.

    Executes synchronous yfinance requests inside a thread pool executor
    to prevent event loop latency.
    """

    def __init__(self, session: AsyncSession, ticker: str = VIX_TICKER):
        """
        Args:
            session: Async SQLAlchemy session.
            ticker: Yahoo Finance ticker symbol for VIX. Default '^VIX'.
        """
        self.session = session
        self.ticker = ticker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, period: str = "10d") -> int:
        """
        Mengunduh data VIX terbaru dan menyimpannya ke DB.

        Args:
            period: String periode yfinance (contoh: '5d', '10d', '1mo').

        Returns:
            Jumlah baris baru yang disimpan.
        """
        logger.info(f"Fetching VIX data for period={period}...")

        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(self._download, period),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            logger.warning("VIX yfinance download timed out after 20.0s")
            return 0
        except Exception as e:
            logger.error(f"VIX download failed: {e}")
            return 0

        if df is None or df.empty:
            logger.warning("VIX download returned empty DataFrame")
            return 0

        saved = await self._save(df)
        logger.info(f"VIX fetch complete. {saved} new records saved.")
        return saved

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _download(self, period: str) -> Optional[pd.DataFrame]:
        """Unduhan yfinance (berjalan secara synchronous di thread pool)."""
        res = yf.download(
            self.ticker,
            period=period,
            progress=False,
            auto_adjust=True,
        )
        return res if isinstance(res, pd.DataFrame) else None

    async def _save(self, df: pd.DataFrame) -> int:
        """Menyimpan record VIX ke DB, mengabaikan tanggal yang sudah ada."""
        saved = 0

        # yfinance mengembalikan MultiIndex columns saat auto_adjust=True
        # Normalisasi ke akses kolom tunggal
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

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

            # Abaikan jika sudah ada
            exists = await self.session.execute(
                select(VIXData.id).where(VIXData.date == record_dt).limit(1)
            )
            if exists.scalar_one_or_none() is not None:
                continue

            record = VIXData(date=record_dt, close=close_val)
            self.session.add(record)
            saved += 1

        if saved:
            from database.safe_ops import safe_commit
            await safe_commit(self.session, label="VIXData")

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
