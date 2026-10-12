# ==============================================================================
# Package: monika.application.services
# File: portfolio_service.py
# ==============================================================================

"""
Portfolio & Position Application Service.
Consolidates position queries, performance metrics, and order history across
all user interfaces (CLI, TUI, Telegram, Web Dashboard).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Position, Order
from database.repositories.position_repository import PositionRepository

logger = logging.getLogger("Monika.Application.PortfolioService")


class PortfolioService:
    """Canonical Application Service managing portfolio state and metrics."""

    @staticmethod
    async def get_open_positions(
        session: AsyncSession,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> List[Position]:
        """Fetch all currently open positions with optional symbol and paper filter."""
        repo = PositionRepository(session)
        return list(await repo.get_open_positions(symbol=symbol, is_paper=is_paper))

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

        if not closed_positions:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "total_realized_pnl": 0.0,
                "profit_factor": 0.0,
                "average_trade_pnl": 0.0,
            }

        total_trades = len(closed_positions)
        winning_trades = sum(1 for p in closed_positions if (p.pnl or 0.0) > 0.0)
        losing_trades = sum(1 for p in closed_positions if (p.pnl or 0.0) < 0.0)
        total_pnl = sum(float(p.pnl or 0.0) for p in closed_positions)
        gross_profit = sum(float(p.pnl or 0.0) for p in closed_positions if (p.pnl or 0.0) > 0.0)
        gross_loss = abs(sum(float(p.pnl or 0.0) for p in closed_positions if (p.pnl or 0.0) < 0.0))

        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": round(win_rate, 2),
            "total_realized_pnl": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "average_trade_pnl": round(avg_pnl, 2),
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

    @staticmethod
    async def get_portfolio_exposure(
        session: AsyncSession,
        is_paper: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Aggregate total exposure, gross lots, net lots, and by-symbol breakdown."""
        positions = await PortfolioService.get_open_positions(session, is_paper=is_paper)
        by_symbol: Dict[str, Dict[str, Any]] = {}
        total_long_lots = 0.0
        total_short_lots = 0.0
        total_unrealized_pnl = 0.0

        for p in positions:
            sym = p.symbol or "UNKNOWN"
            vol = float(p.volume or 0.0)
            pnl = float(p.pnl or 0.0)
            total_unrealized_pnl += pnl
            side = (getattr(p, "direction", None) or getattr(p, "side", "") or "").lower()
            if sym not in by_symbol:
                by_symbol[sym] = {"long_lots": 0.0, "short_lots": 0.0, "net_lots": 0.0, "unrealized_pnl": 0.0, "count": 0}
            by_symbol[sym]["count"] += 1
            by_symbol[sym]["unrealized_pnl"] = round(by_symbol[sym]["unrealized_pnl"] + pnl, 2)
            if side in ("buy", "long"):
                by_symbol[sym]["long_lots"] = round(by_symbol[sym]["long_lots"] + vol, 2)
                total_long_lots += vol
            else:
                by_symbol[sym]["short_lots"] = round(by_symbol[sym]["short_lots"] + vol, 2)
                total_short_lots += vol
            by_symbol[sym]["net_lots"] = round(by_symbol[sym]["long_lots"] - by_symbol[sym]["short_lots"], 2)

        # Calculate Net Currency Exposure (e.g. USD, EUR, GBP, XAU)
        from utils.market.instrument_identity import resolve_instrument_identity
        by_currency: Dict[str, Dict[str, float]] = {}
        for p in positions:
            sym = p.symbol or "UNKNOWN"
            vol = float(p.volume or 0.0)
            side = (getattr(p, "direction", None) or getattr(p, "side", "") or "").lower()
            is_long = side in ("buy", "long")

            ident = resolve_instrument_identity(sym)
            base = ident.base_currency or "UNKNOWN"
            quote = ident.quote_currency or "USD"

            for c_curr in (base, quote):
                if c_curr not in by_currency:
                    by_currency[c_curr] = {"long_lots": 0.0, "short_lots": 0.0, "net_lots": 0.0}

            if is_long:
                by_currency[base]["long_lots"] = round(by_currency[base]["long_lots"] + vol, 2)
                by_currency[quote]["short_lots"] = round(by_currency[quote]["short_lots"] + vol, 2)
            else:
                by_currency[base]["short_lots"] = round(by_currency[base]["short_lots"] + vol, 2)
                by_currency[quote]["long_lots"] = round(by_currency[quote]["long_lots"] + vol, 2)

        for c_curr, data in by_currency.items():
            data["net_lots"] = round(data["long_lots"] - data["short_lots"], 2)

        return {
            "open_positions_count": len(positions),
            "total_gross_lots": round(total_long_lots + total_short_lots, 2),
            "total_net_lots": round(total_long_lots - total_short_lots, 2),
            "total_long_lots": round(total_long_lots, 2),
            "total_short_lots": round(total_short_lots, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "by_symbol": by_symbol,
            "by_currency": by_currency,
        }

