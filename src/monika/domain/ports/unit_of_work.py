# ==============================================================================
# File: domain/ports/unit_of_work.py
# ==============================================================================

"""
Domain Unit of Work Port.

Defines the transactional boundary abstraction for atomic database operations,
isolating application services from direct session management and commit semantics
(Clean Architecture Dependency Inversion Principle).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from monika.domain.ports.repository import (
    ActivityLogRepositoryPort,
    AnalysisRepositoryPort,
    PositionRepositoryPort,
    RiskRepositoryPort,
    SystemConfigRepositoryPort,
    TradeProposalRepositoryPort,
)


@runtime_checkable
class UnitOfWorkPort(Protocol):
    """
    Asynchronous Unit of Work interface guaranteeing atomic business transactions.
    """

    async def __aenter__(self) -> UnitOfWorkPort:
        """Enter transactional context."""
        ...

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Exit transactional context with auto-rollback on failure."""
        ...

    async def commit(self) -> None:
        """Commit all pending database changes within this unit of work."""
        ...

    async def rollback(self) -> None:
        """Rollback all pending changes within this unit of work."""
        ...

    @property
    def positions(self) -> PositionRepositoryPort:
        """Position and order domain repository."""
        ...

    @property
    def trade_proposals(self) -> TradeProposalRepositoryPort:
        """Trade proposals, triggers, and signals repository."""
        ...

    @property
    def system_config(self) -> SystemConfigRepositoryPort:
        """System configurations and safety flags repository."""
        ...

    @property
    def activity_logs(self) -> ActivityLogRepositoryPort:
        """Audit trail and activity log repository."""
        ...

    @property
    def risk(self) -> RiskRepositoryPort:
        """Risk and market data persistence repository."""
        ...
