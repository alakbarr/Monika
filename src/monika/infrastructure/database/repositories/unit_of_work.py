# ==============================================================================
# File: infrastructure/database/repositories/unit_of_work.py
# ==============================================================================

"""
SQLAlchemy Unit of Work Implementation.

Fulfills UnitOfWorkPort by coordinating atomic database transactions across
repositories via an AsyncSession (Clean Architecture Dependency Inversion).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from contextlib import asynccontextmanager
from monika.domain.ports.repository import (
    ActivityLogRepositoryPort,
    AnalysisRepositoryPort,
    MarketDataRepositoryPort,
    PaperTradeRepositoryPort,
    PositionRepositoryPort,
    RiskRepositoryPort,
    SystemConfigRepositoryPort,
    TradeProposalRepositoryPort,
)
from monika.domain.ports.unit_of_work import UnitOfWorkPort
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.repositories.activity_log_repository import ActivityLogRepository
from monika.infrastructure.database.repositories.asset_analysis_repository import SqlAlchemyAssetAnalysisRepository
from monika.infrastructure.database.repositories.market_data_repository import SqlAlchemyMarketDataRepository
from monika.infrastructure.database.repositories.paper_trade_repository import SqlAlchemyPaperTradeRepository
from monika.infrastructure.database.repositories.position_repository import PositionRepository
from monika.infrastructure.database.repositories.risk_repository import SqlAlchemyRiskRepository
from monika.infrastructure.database.repositories.system_config_repository import SystemConfigRepository
from monika.infrastructure.database.repositories.trade_proposal_repository import TradeProposalRepository

logger = logging.getLogger("TradingAgent.Infrastructure.UnitOfWork")


class SqlAlchemyUnitOfWork(UnitOfWorkPort):
    """
    Concrete SQLAlchemy Unit of Work managing database session lifecycle
    and transactional boundaries.
    """

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session: Optional[AsyncSession] = session
        self._is_external_session: bool = session is not None
        self._session_ctx: Optional[Any] = None

        self._positions: Optional[PositionRepositoryPort] = None
        self._trade_proposals: Optional[TradeProposalRepositoryPort] = None
        self._system_config: Optional[SystemConfigRepositoryPort] = None
        self._activity_logs: Optional[ActivityLogRepositoryPort] = None
        self._risk: Optional[RiskRepositoryPort] = None
        self._analyses: Optional[AnalysisRepositoryPort] = None
        self._paper_trades: Optional[PaperTradeRepositoryPort] = None
        self._market_data: Optional[MarketDataRepositoryPort] = None

    @property
    def session(self) -> AsyncSession:
        """Active AsyncSession instance."""
        if self._session is None:
            raise RuntimeError("UnitOfWork session is not active. Use 'async with uow:' context manager.")
        return self._session

    @property
    def positions(self) -> PositionRepositoryPort:
        """Position and order domain repository."""
        if self._positions is None:
            self._positions = PositionRepository(self.session)
        return self._positions

    @property
    def trade_proposals(self) -> TradeProposalRepositoryPort:
        """Trade proposals, triggers, and signals repository."""
        if self._trade_proposals is None:
            self._trade_proposals = TradeProposalRepository(self.session)
        return self._trade_proposals

    @property
    def system_config(self) -> SystemConfigRepositoryPort:
        """System configurations and safety flags repository."""
        if self._system_config is None:
            self._system_config = SystemConfigRepository(self.session)
        return self._system_config

    @property
    def activity_logs(self) -> ActivityLogRepositoryPort:
        """Audit trail and activity log repository."""
        if self._activity_logs is None:
            self._activity_logs = ActivityLogRepository(self.session)
        return self._activity_logs

    @property
    def risk(self) -> RiskRepositoryPort:
        """Risk and market data persistence repository."""
        if self._risk is None:
            self._risk = SqlAlchemyRiskRepository(self.session)
        return self._risk

    @property
    def analyses(self) -> AnalysisRepositoryPort:
        """Asset analysis and fundamental brief repository."""
        if self._analyses is None:
            self._analyses = SqlAlchemyAssetAnalysisRepository(self.session)
        return self._analyses

    @property
    def paper_trades(self) -> PaperTradeRepositoryPort:
        """Simulated paper trade records repository."""
        if self._paper_trades is None:
            self._paper_trades = SqlAlchemyPaperTradeRepository(self.session)
        return self._paper_trades

    @property
    def market_data(self) -> MarketDataRepositoryPort:
        """Market data, OHLCV bars, and rate indicators repository."""
        if self._market_data is None:
            self._market_data = SqlAlchemyMarketDataRepository(self.session)
        return self._market_data

    @asynccontextmanager
    async def nested(self):
        """Savepoint / nested transaction context manager."""
        async with self.session.begin_nested() as savepoint:
            yield savepoint

    async def commit(self) -> None:
        """Commit all pending database changes within this unit of work."""
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        """Rollback all pending database changes within this unit of work."""
        if self._session is not None:
            await self._session.rollback()

    async def __aenter__(self) -> UnitOfWorkPort:
        """Enter transactional context manager."""
        if not self._is_external_session:
            self._session_ctx = get_session()
            self._session = await self._session_ctx.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Exit transactional context manager with auto-rollback on exception."""
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            self._positions = None
            self._trade_proposals = None
            self._system_config = None
            self._activity_logs = None
            self._risk = None
            self._analyses = None
            self._paper_trades = None
            self._market_data = None
            if not self._is_external_session and self._session_ctx is not None:
                await self._session_ctx.__aexit__(exc_type, exc_val, exc_tb)
                self._session = None
                self._session_ctx = None
