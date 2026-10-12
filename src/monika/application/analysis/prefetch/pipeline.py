# ==============================================================================
# File: application/analysis/prefetch/pipeline.py
# ==============================================================================

"""
Unified Prefetch Pipeline.

Provides high-level asynchronous extraction and aggregation of multi-timeframe
market data, indicators, macro intelligence, and execution context.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.infrastructure.database.db import get_session

logger = logging.getLogger("TradingAgent.PrefetchPipeline")


class PrefetchPipeline:
    """
    Unified prefetch pipeline facade for extracting macro, technical, and market context.
    """

    async def get_market_context(
        self,
        symbol: str,
        session: Optional[AsyncSession] = None,
        settings: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Fetch and bundle multi-timeframe market data and indicator state for a symbol.
        """
        clean_symbol = symbol.upper().strip().replace("/", "")
        if session is not None:
            return await self._fetch(clean_symbol, session, settings)

        async with get_session() as new_session:
            return await self._fetch(clean_symbol, new_session, settings)

    async def _fetch(
        self,
        symbol: str,
        session: AsyncSession,
        settings: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        bundler = Stage2DataBundler(session, settings=settings)
        context_str, raw_data = await bundler.fetch_bundle(symbol)
        return {
            "symbol": symbol,
            "context_str": context_str,
            "raw_data": raw_data,
        }


prefetch_pipeline = PrefetchPipeline()
