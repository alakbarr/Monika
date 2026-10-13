# ==============================================================================
# File: domain/ports/repository.py
# ==============================================================================

"""
Domain Repository Ports & Protocols.

Defines pure abstract interfaces for database persistence operations,
strictly isolated from concrete database frameworks, ORMs, and sessions
(Clean Architecture Dependency Inversion Principle).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from monika.domain.entities.order import OrderEntity
from monika.domain.entities.position import PositionEntity
from monika.domain.entities.trade_trigger import TradeTriggerEntity
from monika.domain.risk.ports import RiskDataProviderProtocol


@runtime_checkable
class PositionRepositoryPort(Protocol):
    """Pure domain protocol for Position and Order persistence."""

    async def get_open_positions(
        self,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> Sequence[PositionEntity]:
        """Fetch all currently open positions as domain entities."""
        ...

    async def count_open_positions(self) -> int:
        """Count the total number of open positions."""
        ...

    async def get_by_ticket(self, ticket: int, open_only: bool = False) -> Optional[PositionEntity]:
        """Fetch a position by its MT5 ticket number as domain entity."""
        ...

    async def get_by_id(self, position_id: int) -> Optional[PositionEntity]:
        """Fetch a position by primary key ID as domain entity."""
        ...

    async def get_by_tickets(self, tickets: Sequence[int], open_only: bool = True) -> Sequence[PositionEntity]:
        """Fetch positions matching a list of tickets as domain entities."""
        ...

    async def get_recent_positions(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Sequence[PositionEntity]:
        """Fetch most recent positions as domain entities."""
        ...

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
    ) -> PositionEntity:
        """Create, persist, and return a new trading position domain entity."""
        ...

    async def close_position(
        self,
        ticket: int,
        pnl: Optional[float] = None,
        closed_at: Optional[datetime] = None,
    ) -> Optional[PositionEntity]:
        """Close an existing position by MT5 ticket and return domain entity."""
        ...

    async def update_volume(
        self,
        ticket: int,
        volume: float,
        status: Optional[str] = None,
    ) -> Optional[PositionEntity]:
        """Update volume and optionally status of a position by MT5 ticket."""
        ...

    async def update_sl_tp(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Optional[PositionEntity]:
        """Update SL and/or TP of an open position by MT5 ticket."""
        ...

    async def update_trailing_override(
        self,
        ticket: int,
        override_json: Optional[str],
    ) -> Optional[PositionEntity]:
        """Update trailing override JSON for a position by MT5 ticket."""
        ...

    async def apply_bulk_breakeven(
        self,
        symbol: Optional[str] = None,
    ) -> int:
        """Update Stop Loss to entry price for all open positions matching symbol."""
        ...

    async def get_recent_order_logs(
        self,
        limit: int = 50,
        action: Optional[str] = None,
    ) -> Sequence[Any]:
        """Fetch latest raw broker order audit logs."""
        ...

    async def get_closed_positions(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> Sequence[PositionEntity]:
        """Fetch recently closed positions as domain entities."""
        ...

    async def get_active_orders(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[OrderEntity]:
        """Fetch pending or in-flight orders as domain entities."""
        ...

    async def get_portfolio_metrics(
        self,
        is_paper: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Calculate high-level portfolio performance metrics."""
        ...

    async def get_recent_executed_analysis_ids(self, limit: int = 500) -> Sequence[int]:
        """Fetch recent executed asset analysis IDs from positions."""
        ...

    async def get_recent_order_executed_analysis_ids(self, limit: int = 500) -> Sequence[int]:
        """Fetch recent executed asset analysis IDs from orders."""
        ...


@runtime_checkable
class TradeProposalRepositoryPort(Protocol):
    """Pure domain protocol for TradeTrigger and Signal persistence."""

    async def get_trigger_by_id(self, trigger_id: int) -> Optional[TradeTriggerEntity]:
        """Fetch a conditional trade trigger by ID as domain entity."""
        ...

    async def get_recent_triggers(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> Sequence[TradeTriggerEntity]:
        """Fetch recent trade triggers ordered by creation time as domain entities."""
        ...

    async def create_trigger(
        self,
        trigger_type: str,
        condition_json: str,
        asset_analysis_id: Optional[int] = None,
        status: str = "pending",
    ) -> TradeTriggerEntity:
        """Create, persist, and return a new conditional trade trigger domain entity."""
        ...

    async def update_trigger_status(
        self,
        trigger_id: int,
        status: str,
        fired_at: Optional[datetime] = None,
    ) -> Optional[TradeTriggerEntity]:
        """Update trigger lifecycle status and return domain entity."""
        ...

    async def get_recent_signals(self, limit: int = 50) -> Sequence[Any]:
        """Fetch latest execution signals."""
        ...

    async def get_recent_executed_analysis_ids(self, limit: int = 500) -> Sequence[int]:
        """Fetch recent executed asset analysis IDs from signals."""
        ...


@runtime_checkable
class ActivityLogRepositoryPort(Protocol):
    """Pure domain protocol for ActivityLog audit logging."""

    async def log_activity(
        self,
        category: str,
        description: str,
        actor: str = "system",
        related_id: Optional[int] = None,
    ) -> Any:
        """Create and persist an activity log entry."""
        ...

    async def get_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Sequence[Any]:
        """Fetch latest activity log records with optional filtering."""
        ...

    async def count_by_category(self, category: str) -> int:
        """Count total log entries in a given category."""
        ...


@runtime_checkable
class SystemConfigRepositoryPort(Protocol):
    """Pure domain protocol for runtime SystemConfig persistence."""

    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch raw string configuration value by key."""
        ...

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """Fetch configuration value parsed as boolean."""
        ...

    async def set(self, key: str, value: str, description: Optional[str] = None) -> Any:
        """Upsert a configuration entry atomically."""
        ...

    async def get_all(self) -> Sequence[Any]:
        """Fetch all configuration entries."""
        ...

    async def is_kill_switch_active(self) -> bool:
        """Check whether the global emergency kill switch is engaged."""
        ...

    async def set_kill_switch(self, active: bool) -> None:
        """Engage or disengage the global emergency kill switch."""
        ...

    async def is_system_paused(self) -> bool:
        """Check whether trading operations are temporarily paused."""
        ...

    async def set_system_paused(self, paused: bool) -> None:
        """Pause or unpause trading operations."""
        ...

    async def get_risk_override(self) -> Optional[str]:
        """Fetch active risk override payload if configured."""
        ...

    async def set_risk_override(self, override_json: Optional[str]) -> None:
        """Set or clear dynamic risk parameter override."""
        ...


@runtime_checkable
class RiskRepositoryPort(RiskDataProviderProtocol, Protocol):
    """Pure domain protocol for Risk state and metric persistence."""
    ...


@runtime_checkable
class AnalysisRepositoryPort(Protocol):
    """Pure domain protocol for Analysis and deduplication queries."""

    async def get_recent_executed_analysis_ids(self, limit: int = 500) -> Sequence[int]:
        """Fetch recent executed asset analysis IDs."""
        ...
