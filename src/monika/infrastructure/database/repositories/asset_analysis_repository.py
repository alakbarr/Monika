# ==============================================================================
# File: infrastructure/database/repositories/asset_analysis_repository.py
# ==============================================================================

"""
Concrete SQLAlchemy implementation of AnalysisRepositoryPort.
Provides encapsulated persistence for AssetAnalysis and macroeconomic briefs.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.ports.repository import AnalysisRepositoryPort
from monika.infrastructure.database.domain_models.analysis import AssetAnalysis
from monika.infrastructure.database.domain_models.trading import Position

logger = logging.getLogger("TradingAgent.AssetAnalysisRepository")


class SqlAlchemyAssetAnalysisRepository(AnalysisRepositoryPort):
    """Encapsulates all database operations for AssetAnalysis entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, analysis_id: int) -> Optional[AssetAnalysis]:
        """Fetch an AssetAnalysis record by primary key ID."""
        return await self.session.get(AssetAnalysis, analysis_id)

    async def get_recent_executed_analysis_ids(self, limit: int = 500) -> Sequence[int]:
        """Fetch distinct analysis IDs that resulted in real positions (deduplication)."""
        stmt = (
            select(Position.analysis_id)
            .where(Position.analysis_id.is_not(None))
            .distinct()
            .order_by(desc(Position.id))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [aid for aid in res.scalars().all() if aid is not None]

    async def get_latest_by_symbol(self, symbol: str) -> Optional[AssetAnalysis]:
        """Fetch most recent asset analysis evaluation for a symbol."""
        stmt = (
            select(AssetAnalysis)
            .where(AssetAnalysis.symbol == symbol)
            .order_by(desc(AssetAnalysis.generated_at))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
