"""
Trade Proposal Repository.

Encapsulates database access for trade triggers, conditional orders, and MT5 signals.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.entities.trade_trigger import TradeTriggerEntity
from monika.domain.ports.repository import TradeProposalRepositoryPort
from monika.infrastructure.database.models import MT5Signal, TradeTrigger


class TradeProposalRepository(TradeProposalRepositoryPort):
    """Repository managing TradeTrigger and MT5Signal domain entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_trigger_by_id(self, trigger_id: int) -> Optional[TradeTriggerEntity]:
        """Fetch a conditional trade trigger by ID as domain entity."""
        stmt = select(TradeTrigger).where(TradeTrigger.id == trigger_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        return TradeTriggerEntity.from_orm(row) if row else None

    async def get_recent_triggers(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> Sequence[TradeTriggerEntity]:
        """Fetch recent trade triggers ordered by creation time as domain entities."""
        stmt = select(TradeTrigger)
        if status:
            stmt = stmt.where(TradeTrigger.status == status)
        stmt = stmt.order_by(TradeTrigger.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return [TradeTriggerEntity.from_orm(t) for t in res.scalars().all()]

    async def create_trigger(
        self,
        trigger_type: str,
        condition_json: str,
        asset_analysis_id: Optional[int] = None,
        status: str = "pending",
    ) -> TradeTriggerEntity:
        """Create, persist, and return a new conditional trade trigger domain entity."""
        trigger = TradeTrigger(
            trigger_type=trigger_type,
            condition_json=condition_json,
            asset_analysis_id=asset_analysis_id,
            status=status,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(trigger)
        await self.session.flush()
        return TradeTriggerEntity.from_orm(trigger)

    async def update_trigger_status(
        self,
        trigger_id: int,
        status: str,
        fired_at: Optional[datetime] = None,
    ) -> Optional[TradeTriggerEntity]:
        """Update trigger lifecycle status and return domain entity."""
        stmt = select(TradeTrigger).where(TradeTrigger.id == trigger_id)
        res = await self.session.execute(stmt)
        trigger = res.scalar_one_or_none()
        if not trigger:
            return None
        trigger.status = status
        if status == "fired":
            trigger.fired_at = fired_at or datetime.now(timezone.utc)
        await self.session.flush()
        return TradeTriggerEntity.from_orm(trigger)

    async def get_recent_signals(self, limit: int = 50) -> Sequence[MT5Signal]:
        """Fetch latest MT5 execution signals."""
        stmt = select(MT5Signal).order_by(MT5Signal.id.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_recent_executed_analysis_ids(self, limit: int = 500) -> Sequence[int]:
        """Fetch recent executed asset analysis IDs from signals."""
        stmt = (
            select(MT5Signal.asset_analysis_id)
            .where(MT5Signal.asset_analysis_id.isnot(None))
            .order_by(MT5Signal.id.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [int(aid) for aid in res.scalars().all() if aid is not None]
