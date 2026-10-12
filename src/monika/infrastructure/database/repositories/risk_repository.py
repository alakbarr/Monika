# ==============================================================================
# File: infrastructure/database/repositories/risk_repository.py
# ==============================================================================

"""
SQLAlchemy Risk Repository.

Implements RiskDataProviderProtocol by isolating SQL queries and database access
for account metrics, open positions, VIX indicators, and risk states from the pure domain.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.risk.ports import RiskDataProviderProtocol
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import (
    EquityDrawdownSnapshot,
    Order,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    SystemConfig,
    TradeOutcome,
    UserPreference,
    VIXData,
)

logger = logging.getLogger("TradingAgent.RiskRepository")


class SqlAlchemyRiskRepository(RiskDataProviderProtocol):
    """
    Concrete database repository fulfilling RiskDataProviderProtocol.
    """

    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session: Optional[AsyncSession] = session
        self.settings: Dict[str, Any] = settings or {}

    async def get_open_positions(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of active open positions as standardized dictionaries."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_open_positions(sess, is_paper)

        async with get_session() as new_session:
            return await self._query_open_positions(new_session, is_paper)

    async def _query_open_positions(
        self,
        session: AsyncSession,
        is_paper: bool,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if is_paper:
            stmt = select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
            res = await session.execute(stmt)
            for rec in res.scalars().all():
                results.append({
                    "id": rec.id,
                    "symbol": rec.symbol,
                    "direction": rec.direction,
                    "lots": float(rec.lot_size),
                    "entry_price": float(rec.entry_price or 0.0),
                    "stop_loss": float(rec.stop_loss or 0.0) if rec.stop_loss else None,
                    "take_profit": float(rec.take_profit or 0.0) if rec.take_profit else None,
                    "is_paper": True,
                })
        else:
            stmt = select(Position).where(Position.status == "open")
            res = await session.execute(stmt)
            for pos in res.scalars().all():
                ticket = pos.mt5_ticket or pos.id
                results.append({
                    "id": ticket,
                    "ticket": ticket,
                    "symbol": pos.symbol,
                    "direction": str(pos.direction).upper(),
                    "lots": float(pos.volume or 0.0),
                    "entry_price": float(pos.entry_price or 0.0),
                    "stop_loss": float(pos.sl or 0.0) if pos.sl else None,
                    "take_profit": float(pos.tp or 0.0) if pos.tp else None,
                    "is_paper": False,
                })
        return results

    async def get_account_equity_and_balance(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> Tuple[float, float]:
        """Return (equity, balance) in USD."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_account_equity_and_balance(sess, is_paper)

        async with get_session() as new_session:
            return await self._query_account_equity_and_balance(new_session, is_paper)

    async def _query_account_equity_and_balance(
        self,
        session: AsyncSession,
        is_paper: bool,
    ) -> Tuple[float, float]:
        if is_paper:
            paper_initial = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
            stmt = select(func.sum(PaperTradeRecord.pnl_pct)).where(PaperTradeRecord.status == "closed")
            res = await session.execute(stmt)
            total_pnl_pct = float(res.scalar() or 0.0)
            balance = paper_initial * (1.0 + total_pnl_pct / 100.0)
            return balance, balance

        # Live account state query via EquityDrawdownSnapshot
        stmt = select(EquityDrawdownSnapshot).order_by(desc(EquityDrawdownSnapshot.timestamp)).limit(1)
        res = await session.execute(stmt)
        acc = res.scalar_one_or_none()
        if acc:
            return float(acc.equity or 0.0), float(acc.balance or 0.0)

        # Fail-closed: 0.0 if unrecorded
        return 0.0, 0.0

    async def get_daily_trades_count(
        self,
        symbol: Optional[str] = None,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> int:
        """Return count of trades created today."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_daily_trades_count(sess, symbol, is_paper)

        async with get_session() as new_session:
            return await self._query_daily_trades_count(new_session, symbol, is_paper)

    async def _query_daily_trades_count(
        self,
        session: AsyncSession,
        symbol: Optional[str],
        is_paper: bool,
    ) -> int:
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

        if is_paper:
            stmt = select(func.count(PaperTradeRecord.id)).where(PaperTradeRecord.opened_at >= today_start)
            if symbol:
                stmt = stmt.where(PaperTradeRecord.symbol == symbol.upper().strip())
        else:
            stmt = select(func.count(Order.id)).where(Order.created_at >= today_start)
            if symbol:
                stmt = stmt.where(Order.symbol == symbol.upper().strip())

        res = await session.execute(stmt)
        return int(res.scalar() or 0)

    async def get_recent_drawdown(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> float:
        """Calculate intraday drawdown percentage relative to peak equity."""
        equity, balance = await self.get_account_equity_and_balance(is_paper=is_paper, session=session)
        if balance <= 0.0:
            return 0.0
        if equity >= balance:
            return 0.0
        return (balance - equity) / balance

    async def get_recent_vix(
        self,
        session: Optional[Any] = None,
    ) -> Optional[float]:
        """Retrieve most recent VIX index value."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_vix(sess)

        async with get_session() as new_session:
            return await self._query_vix(new_session)

    async def _query_vix(self, session: AsyncSession) -> Optional[float]:
        stmt = select(VIXData).order_by(desc(VIXData.date)).limit(1)
        res = await session.execute(stmt)
        vix_row = res.scalar_one_or_none()
        if vix_row and vix_row.close is not None:
            return float(vix_row.close)
        return None

    async def get_system_config_value(
        self,
        key: str,
        default: Any = None,
        session: Optional[Any] = None,
    ) -> Any:
        """Retrieve configuration parameter from SystemConfig."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_sys_config(sess, key, default)

        async with get_session() as new_session:
            return await self._query_sys_config(new_session, key, default)

    async def _query_sys_config(self, session: AsyncSession, key: str, default: Any) -> Any:
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        res = await session.execute(stmt)
        cfg = res.scalar_one_or_none()
        if cfg and cfg.value is not None:
            return cfg.value
        return default

    async def get_user_preference(
        self,
        key: str,
        default: Any = None,
        session: Optional[Any] = None,
    ) -> Any:
        """Retrieve user preference from UserPreference table."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_user_preference(sess, key, default)

        async with get_session() as new_session:
            return await self._query_user_preference(new_session, key, default)

    async def _query_user_preference(self, session: AsyncSession, key: str, default: Any) -> Any:
        stmt = select(UserPreference).where(UserPreference.key == key)
        res = await session.execute(stmt)
        pref = res.scalar_one_or_none()
        if pref and pref.value_json is not None:
            return pref.value_json
        return default

    async def get_recent_price_bars(
        self,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 100,
        session: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve price history OHLCV bars."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_price_bars(sess, symbol, timeframe, limit)

        async with get_session() as new_session:
            return await self._query_price_bars(new_session, symbol, timeframe, limit)

    async def _query_price_bars(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol.upper().strip(), PriceOHLCV.timeframe == timeframe)
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(limit)
        )
        res = await session.execute(stmt)
        bars: List[Dict[str, Any]] = []
        for row in reversed(res.scalars().all()):
            bars.append({
                "time": row.timestamp.isoformat() if hasattr(row.timestamp, "isoformat") else str(row.timestamp),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume or 0.0),
            })
        return bars

    async def get_loss_streak(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> int:
        """Calculate consecutive realized loss streak."""
        sess: Optional[AsyncSession] = session or self.session
        if sess is not None:
            return await self._query_loss_streak(sess, is_paper)

        async with get_session() as new_session:
            return await self._query_loss_streak(new_session, is_paper)

    async def _query_loss_streak(self, session: AsyncSession, is_paper: bool) -> int:
        if is_paper:
            stmt = (
                select(PaperTradeRecord.pnl_pct)
                .where(PaperTradeRecord.status == "closed")
                .order_by(desc(PaperTradeRecord.closed_at))
                .limit(20)
            )
            res = await session.execute(stmt)
            pnls = res.scalars().all()
            streak = 0
            for pnl in pnls:
                if pnl is not None and float(pnl) < 0.0:
                    streak += 1
                else:
                    break
            return streak

        stmt = (
            select(TradeOutcome.pnl_usd)
            .order_by(desc(TradeOutcome.closed_at))
            .limit(20)
        )
        res = await session.execute(stmt)
        pnls = res.scalars().all()
        streak = 0
        for pnl in pnls:
            if pnl is not None and float(pnl) < 0.0:
                streak += 1
            else:
                break
        return streak
