# ==============================================================================
# Package: monika.application.services
# File: market_intel_service.py
# ==============================================================================

"""
Market Intelligence Application Service.
Consolidates market data fetching, Alpha Factor evaluations, regime classifications,
and economic calendar intelligence for quantitative strategies and Special Council agents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.indicators.alpha_zoo.vector_factor_engine import (
    VectorFactorEngine,
    VectorFactorResult,
    get_vector_factor_engine,
)
from monika.infrastructure.database.models import EconomicCalendar, PriceOHLCV

logger = logging.getLogger("Monika.Application.MarketIntelService")


@dataclass(frozen=True)
class CandleDTO:
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: Any = None


@dataclass(frozen=True)
class EconomicEventDTO:
    event_name: str
    currency: str
    impact: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    event_time: Any = None


class MarketIntelService:
    """Canonical Application Service orchestrating market telemetry and Alpha Factor flows."""

    @classmethod
    def evaluate_alpha_factors(
        cls,
        symbol: str,
        df: pd.DataFrame,
        regime: str = "ranging",
        top_k: int = 5,
    ) -> VectorFactorResult:
        """
        Evaluate quantitative alpha factor library on asset OHLCV bars using
        vectorized in-memory engine. Returns top factors and prompt context.
        """
        engine = get_vector_factor_engine()
        return engine.evaluate(df=df, symbol=symbol, regime=regime, top_k=top_k)

    @classmethod
    async def get_recent_candles(
        cls,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 100,
    ) -> List[CandleDTO]:
        """Fetch latest cached OHLCV candles from persistence store as detached DTOs."""
        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol.upper(), PriceOHLCV.timeframe == timeframe.upper())
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        return list(
            reversed(
                [
                    CandleDTO(
                        symbol=r.symbol,
                        timeframe=r.timeframe,
                        open=float(r.open),
                        high=float(r.high),
                        low=float(r.low),
                        close=float(r.close),
                        volume=float(r.volume or 0.0),
                        timestamp=r.timestamp,
                    )
                    for r in rows
                ]
            )
        )

    @classmethod
    async def get_upcoming_economic_events(
        cls,
        session: AsyncSession,
        currencies: Optional[List[str]] = None,
        impact_levels: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[EconomicEventDTO]:
        """Fetch upcoming economic calendar news events as detached DTOs."""
        stmt = select(EconomicCalendar)
        if currencies:
            upper_curr = [c.upper() for c in currencies]
            stmt = stmt.where(EconomicCalendar.currency.in_(upper_curr))
        if impact_levels:
            lower_impact = [i.lower() for i in impact_levels]
            stmt = stmt.where(EconomicCalendar.impact.in_(lower_impact))
        stmt = stmt.order_by(EconomicCalendar.event_time.asc()).limit(limit)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        return [
            EconomicEventDTO(
                event_name=r.event_name,
                currency=r.currency,
                impact=r.impact,
                actual=r.actual,
                forecast=r.forecast,
                previous=r.previous,
                event_time=r.event_time,
            )
            for r in rows
        ]
