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
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.entities.position import PositionEntity
from monika.domain.entities.order import OrderEntity
from monika.infrastructure.database.repositories.position_repository import PositionRepository

logger = logging.getLogger("Monika.Application.PortfolioService")


class PortfolioService:
    """Canonical Application Service managing portfolio state and metrics."""

    @staticmethod
    async def get_open_positions(
        session: AsyncSession,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> List[PositionEntity]:
        """Fetch all currently open positions with optional symbol and paper filter."""
        repo = PositionRepository(session)
        return list(await repo.get_open_positions(symbol=symbol, is_paper=is_paper))

    @staticmethod
    async def get_closed_positions(
        session: AsyncSession,
        limit: int = 50,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> List[PositionEntity]:
        """Fetch recently closed positions with pagination and filters."""
        repo = PositionRepository(session)
        return list(await repo.get_closed_positions(limit=limit, symbol=symbol, is_paper=is_paper))

    @staticmethod
    async def get_portfolio_metrics(
        session: AsyncSession,
        is_paper: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Calculate high-level portfolio performance metrics (Win Rate, Total PnL, Volume)."""
        repo = PositionRepository(session)
        return await repo.get_portfolio_metrics(is_paper=is_paper)

    @staticmethod
    async def get_active_orders(
        session: AsyncSession,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[OrderEntity]:
        """Fetch pending or in-flight orders."""
        repo = PositionRepository(session)
        return list(await repo.get_active_orders(symbol=symbol, limit=limit))

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
        from monika.domain.market.instrument_identity import resolve_instrument_identity
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

