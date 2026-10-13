"""
Activity Log Repository.

Encapsulates database access for audit activity logging.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import ActivityLog


class ActivityLogRepository:
    """Repository managing ActivityLog audit entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_activity(
        self,
        category: str,
        description: str,
        actor: str = "system",
        related_id: Optional[int] = None,
    ) -> ActivityLog:
        """Create and persist an activity log entry."""
        entry = ActivityLog(
            category=category,
            description=description,
            actor=actor,
            related_id=related_id,
            timestamp=datetime.now(timezone.utc),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Sequence[ActivityLog]:
        """Fetch latest activity log records with optional filtering."""
        stmt = select(ActivityLog)
        if category:
            stmt = stmt.where(ActivityLog.category == category)
        if actor:
            stmt = stmt.where(ActivityLog.actor == actor)
        stmt = stmt.order_by(ActivityLog.timestamp.desc()).offset(offset).limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def count_by_category(self, category: str) -> int:
        """Count total log entries in a given category."""
        stmt = select(func.count(ActivityLog.id)).where(ActivityLog.category == category)
        res = await self.session.execute(stmt)
        return int(res.scalar() or 0)
