# ==============================================================================
# File: services/portfolio_service.py
# ==============================================================================

"""
Portfolio & Position Application Service.
Consolidates direct database position and order queries from UI layers
(Telegram Bot, CLI, TUI, Dashboard) into a unified service layer.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Position, Order


class PortfolioService:
    """Service encapsulating portfolio query logic and analytics."""

    @staticmethod
    async def get_open_positions(
        session: AsyncSession,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> List[Position]:
        """Fetch all currently open positions, with optional symbol and paper/live filter."""
        stmt = select(Position).where(Position.status == "open")
        if symbol:
            stmt = stmt.where(Position.symbol == symbol.upper())
        if is_paper is not None:
            stmt = stmt.where(Position.is_paper == is_paper)
        stmt = stmt.order_by(desc(Position.opened_at))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_closed_positions(
        session: AsyncSession,
        limit: int = 50,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> List[Position]:
        """Fetch recently closed positions with pagination and filters."""
        stmt = select(Position).where(Position.status == "closed")
        if symbol:
            stmt = stmt.where(Position.symbol == symbol.upper())
        if is_paper is not None:
            stmt = stmt.where(Position.is_paper == is_paper)
        stmt = stmt.order_by(desc(Position.closed_at)).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_portfolio_metrics(
        session: AsyncSession,
        is_paper: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Calculate high-level portfolio performance metrics (Win Rate, Total PnL, Volume)."""
        stmt = select(Position).where(Position.status == "closed")
        if is_paper is not None:
            stmt = stmt.where(Position.is_paper == is_paper)
        result = await session.execute(stmt)
        closed_positions = list(result.scalars().all())

        total_trades = len(closed_positions)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "profit_factor": 0.0,
                "total_volume": 0.0,
            }

        wins = [p for p in closed_positions if (p.pnl or 0.0) > 0]
        losses = [p for p in closed_positions if (p.pnl or 0.0) < 0]
        gross_profit = sum(p.pnl or 0.0 for p in wins)
        gross_loss = abs(sum(p.pnl or 0.0 for p in losses))
        total_pnl = sum(p.pnl or 0.0 for p in closed_positions)
        total_vol = sum(p.volume or 0.0 for p in closed_positions)

        win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        return {
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "total_volume": round(total_vol, 2),
        }

    @staticmethod
    async def get_active_orders(
        session: AsyncSession,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[Order]:
        """Fetch pending or in-flight orders."""
        stmt = select(Order).where(Order.status.in_(["pending", "executing", "submitted"]))
        if symbol:
            stmt = stmt.where(Order.symbol == symbol.upper())
        stmt = stmt.order_by(desc(Order.created_at)).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())
