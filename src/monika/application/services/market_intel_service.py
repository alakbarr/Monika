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
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import EconomicCalendar, PriceOHLCV
from indicators.alpha_zoo.vector_factor_engine import (
    VectorFactorEngine,
    VectorFactorResult,
    get_vector_factor_engine,
)

logger = logging.getLogger("Monika.Application.MarketIntelService")


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
    ) -> List[PriceOHLCV]:
        """Fetch latest cached OHLCV candles from persistence store."""
        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol.upper(), PriceOHLCV.timeframe == timeframe.upper())
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(reversed(list(result.scalars().all())))

    @classmethod
    async def get_upcoming_economic_events(
        cls,
        session: AsyncSession,
        currencies: Optional[List[str]] = None,
        impact_levels: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[EconomicCalendar]:
        """Fetch upcoming economic calendar news events to inform news safety filters."""
        stmt = select(EconomicCalendar)
        if currencies:
            upper_curr = [c.upper() for c in currencies]
            stmt = stmt.where(EconomicCalendar.currency.in_(upper_curr))
        if impact_levels:
            lower_impact = [i.lower() for i in impact_levels]
            stmt = stmt.where(EconomicCalendar.impact.in_(lower_impact))
        stmt = stmt.order_by(EconomicCalendar.event_time.asc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())
