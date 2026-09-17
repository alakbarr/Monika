# ==============================================================================
# File: data_sources/dxy_yfinance.py
# ==============================================================================

"""
DXY (US Dollar Index) Fetcher using yfinance.
The US Dollar Index tracks the relative performance of USD against major trade partner currencies.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DXYData

logger = logging.getLogger("TradingAgent.DXY")

DXY_TICKER = "DX-Y.NYB"


class DXYFetcher:
    """Fetches US Dollar Index (DXY) settlement series from Yahoo Finance."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ticker = DXY_TICKER

    async def fetch(self, period: str = "10d") -> int:
        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(self._download, period),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            logger.warning("DXY yfinance download timed out after 20.0s")
            return 0
        except Exception as e:
            logger.error(f"DXY download failed: {e}")
            return 0

        if df is None or df.empty:
            return 0

        return await self._save(df)

    def _download(self, period: str) -> Optional[pd.DataFrame]:
        res = yf.download(self.ticker, period=period, progress=False, auto_adjust=True)
        return res if isinstance(res, pd.DataFrame) else None

    async def _save(self, df: pd.DataFrame) -> int:
        """Menyimpan data DXY ke database."""
        from database.models import DXYData
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        saved = 0
        for idx, row in df.iterrows():
            if isinstance(idx, (pd.Timestamp, datetime)):
                record_dt = datetime(idx.year, idx.month, idx.day, tzinfo=timezone.utc)
            else:
                ts = pd.Timestamp(str(idx))
                record_dt = datetime(int(ts.year), int(ts.month), int(ts.day), tzinfo=timezone.utc)
            
            close_val = None
            for col in ["Close", "Adj Close", "close"]:
                if col in row and pd.notna(row[col]):
                    close_val = float(row[col])
                    break

            if close_val is None:
                continue

            exists = await self.session.execute(
                select(DXYData.id).where(DXYData.date == record_dt).limit(1)
            )
            if exists.scalar_one_or_none() is not None:
                continue

            self.session.add(DXYData(date=record_dt, close=close_val))
            saved += 1

        if saved:
            from database.safe_ops import safe_commit
            await safe_commit(self.session, label="DXYData")
        return saved

    async def get_latest(self) -> Optional[dict]:
        """
        Mengembalikan record DXY paling baru dari database.

        Returns:
            Dict dengan kunci 'date' dan 'close', atau None jika data kosong.
        """
        result = await self.session.execute(
            select(DXYData).order_by(DXYData.date.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {"date": row.date, "close": row.close}
