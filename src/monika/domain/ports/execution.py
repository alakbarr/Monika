# ==============================================================================
# File: domain/ports/execution.py
# ==============================================================================

"""
Domain Broker & Execution Port.

Defines pure abstract interfaces for broker order placement, position query,
quote fetching, and account state inspection (Dependency Inversion Principle).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class BrokerPort(Protocol):
    """Standardized pure domain protocol for broker operations."""

    async def get_tick(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest tick quote (keys: symbol, bid, ask, last, spread, time)."""
        ...

    async def submit_order(self, order: Any, **kwargs: Any) -> Dict[str, Any]:
        """Submit an order for execution."""
        ...

    async def cancel_order(self, client_order_id: str) -> bool:
        """Cancel a pending/in-flight order."""
        ...

    async def get_orders(self, symbol: Optional[str] = None) -> Sequence[Dict[str, Any]]:
        """Return list of active pending orders."""
        ...

    async def get_positions(self) -> Sequence[Dict[str, Any]]:
        """Return list of all open positions."""
        ...

    async def get_account_info(self) -> Dict[str, Any]:
        """Return account financial status (balance, equity, margin, free_margin, leverage)."""
        ...

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> Dict[str, Any]:
        """Close an open position."""
        ...

    async def close_all_positions(self, comment: str = "KillSwitch") -> Dict[str, Any]:
        """Close all open positions on the broker."""
        ...


# Semantic alias for execution subsystems
ExecutionPort = BrokerPort
