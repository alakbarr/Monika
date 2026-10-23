# ==============================================================================
# File: infrastructure/database/repositories/paper_trade_repository.py
# ==============================================================================

"""
Concrete SQLAlchemy implementation of PaperTradeRepositoryPort.
Provides encapsulated persistence for simulated paper trade records.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Optional, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.ports.repository import PaperTradeRepositoryPort
from monika.infrastructure.database.domain_models.trading import PaperTradeRecord

logger = logging.getLogger("TradingAgent.PaperTradeRepository")


class SqlAlchemyPaperTradeRepository(PaperTradeRepositoryPort):
    """Encapsulates all database operations for PaperTradeRecord entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_open_records(self, symbol: Optional[str] = None) -> Sequence[PaperTradeRecord]:
        """Fetch active open paper trades, optionally filtered by symbol."""
        stmt = select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
        if symbol:
            stmt = stmt.where(PaperTradeRecord.symbol == symbol)
        stmt = stmt.order_by(desc(PaperTradeRecord.opened_at))
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_by_id(self, record_id: int) -> Optional[PaperTradeRecord]:
        """Fetch a specific paper trade record by primary key ID."""
        return await self.session.get(PaperTradeRecord, record_id)

    async def create_record(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        risk_pct: float = 0.75,
        analysis_id: Optional[int] = None,
        stated_entry_price: Optional[float] = None,
        requested_lot: Optional[float] = None,
        slippage_applied: float = 0.0,
    ) -> PaperTradeRecord:
        """Create and persist a new simulated paper trade record."""
        record = PaperTradeRecord(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_pct=risk_pct,
            analysis_id=analysis_id,
            stated_entry_price=stated_entry_price or entry_price,
            requested_lot=requested_lot,
            slippage_applied=slippage_applied,
            status="open",
            opened_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def close_record(
        self,
        record_id: int,
        exit_price: float,
        pnl_pct: float,
        exit_reason: str = "manual",
    ) -> Optional[PaperTradeRecord]:
        """Close an existing paper trade record with exit price and calculated PnL."""
        record = await self.get_by_id(record_id)
        if record is None:
            return None
        record.status = "closed"
        record.exit_price = exit_price
        record.pnl_pct = pnl_pct
        record.exit_reason = exit_reason
        record.closed_at = datetime.now(UTC)
        await self.session.flush()
        return record
