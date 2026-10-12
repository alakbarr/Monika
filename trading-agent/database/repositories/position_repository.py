"""
Position Repository.

Encapsulates database access for trading positions and order records.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Position, Order, OrderLog


class PositionRepository:
    """Repository handling Position and Order domain entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_open_positions(self, symbol: Optional[str] = None) -> Sequence[Position]:
        """Fetch all currently open positions, optionally filtered by symbol."""
        stmt = select(Position).where(Position.status == "open")
        if symbol:
            stmt = stmt.where(Position.symbol == symbol)
        stmt = stmt.order_by(Position.opened_at.desc())
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def count_open_positions(self) -> int:
        """Count the total number of open positions."""
        stmt = select(func.count(Position.id)).where(Position.status == "open")
        res = await self.session.execute(stmt)
        return int(res.scalar() or 0)

    async def get_by_ticket(self, ticket: int, open_only: bool = False) -> Optional[Position]:
        """Fetch a position by its MT5 ticket number."""
        stmt = select(Position).where(Position.mt5_ticket == ticket)
        if open_only:
            stmt = stmt.where(Position.status == "open")
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id(self, position_id: int) -> Optional[Position]:
        """Fetch a position by primary key ID."""
        stmt = select(Position).where(Position.id == position_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_tickets(self, tickets: Sequence[int], open_only: bool = True) -> Sequence[Position]:
        """Fetch positions matching a list of tickets."""
        if not tickets:
            return []
        stmt = select(Position).where(Position.mt5_ticket.in_(tickets))
        if open_only:
            stmt = stmt.where(Position.status == "open")
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_recent_positions(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Sequence[Position]:
        """Fetch most recent positions ordered by opening timestamp."""
        stmt = select(Position)
        if symbol:
            stmt = stmt.where(Position.symbol == symbol)
        if status and status != "all":
            stmt = stmt.where(Position.status == status)
        stmt = stmt.order_by(Position.opened_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def create_position(
        self,
        symbol: str,
        direction: str,
        volume: float,
        entry_price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        mt5_ticket: Optional[int] = None,
        is_paper: bool = False,
        order_id: Optional[str] = None,
        analysis_id: Optional[int] = None,
        pair_group_id: Optional[str] = None,
    ) -> Position:
        """Create and persist a new trading position."""
        pos = Position(
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            mt5_ticket=mt5_ticket,
            is_paper=is_paper,
            order_id=order_id,
            analysis_id=analysis_id,
            pair_group_id=pair_group_id,
            status="open",
            opened_at=datetime.now(timezone.utc),
        )
        self.session.add(pos)
        await self.session.flush()
        return pos

    async def close_position(
        self,
        ticket: int,
        pnl: Optional[float] = None,
        closed_at: Optional[datetime] = None,
    ) -> Optional[Position]:
        """Close an existing position by MT5 ticket."""
        pos = await self.get_by_ticket(ticket, open_only=True)
        if not pos:
            return None
        pos.status = "closed"
        pos.pnl = pnl
        pos.closed_at = closed_at or datetime.now(timezone.utc)
        await self.session.flush()
        return pos

    async def get_recent_order_logs(self, limit: int = 50) -> Sequence[OrderLog]:
        """Fetch latest raw broker order audit logs."""
        stmt = select(OrderLog).order_by(OrderLog.timestamp.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all()
