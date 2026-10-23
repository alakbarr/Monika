# ==============================================================================
# File: infrastructure/database/repositories/market_data_repository.py
# ==============================================================================

"""
Concrete SQLAlchemy implementation of MarketDataRepositoryPort.
Provides encapsulated persistence for OHLCV bars, macroeconomic rates, and market primitives.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.ports.repository import MarketDataRepositoryPort
from monika.infrastructure.database.domain_models.market import (
    DXYData,
    PriceOHLCV,
    TreasuryYield,
    VIXData,
)

logger = logging.getLogger("TradingAgent.MarketDataRepository")


class SqlAlchemyMarketDataRepository(MarketDataRepositoryPort):
    """Encapsulates all database operations for market indicators and price bars."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_recent_bars(self, symbol: str, timeframe: str = "H1", limit: int = 100) -> Sequence[PriceOHLCV]:
        """Fetch historical OHLCV price bars ordered by timestamp ascending."""
        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        bars = list(res.scalars().all())
        bars.reverse()
        return bars

    async def get_latest_vix(self) -> Optional[float]:
        """Fetch latest available VIX index level."""
        stmt = select(VIXData.close).order_by(desc(VIXData.date)).limit(1)
        res = await self.session.execute(stmt)
        val = res.scalar_one_or_none()
        return float(val) if val is not None else None

    async def get_latest_dxy(self) -> Optional[float]:
        """Fetch latest available DXY index close."""
        stmt = select(DXYData.close).order_by(desc(DXYData.date)).limit(1)
        res = await self.session.execute(stmt)
        val = res.scalar_one_or_none()
        return float(val) if val is not None else None

    async def get_latest_yield(self, tenor: str = "10Y") -> Optional[float]:
        """Fetch latest treasury yield percent for specified tenor."""
        stmt = (
            select(TreasuryYield.yield_percent)
            .where(TreasuryYield.tenor == tenor)
            .order_by(desc(TreasuryYield.date))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        val = res.scalar_one_or_none()
        return float(val) if val is not None else None
