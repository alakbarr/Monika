"""
File: trading-agent/agent/turn_lease_manager.py

Symbol Turn Lease & Event Coalescence Manager.
Prevents concurrent analysis collisions across schedulers on identical asset symbols.
Automatically coalesces reactive market shocks and breaking news directly into the
active analysis turn's steering queue without restarting the analysis cycle.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.TurnLeaseManager")


class SymbolLease:
    """Represents a durable time-bounded analysis lease on a trading symbol."""

    def __init__(
        self,
        symbol: str,
        holder_id: str,
        ttl_seconds: float = 300.0,
        active_harness: Optional[Any] = None,
    ):
        self.symbol = symbol.upper()
        self.holder_id = holder_id
        self.acquired_at = datetime.now(timezone.utc)
        self.expires_at = self.acquired_at + timedelta(seconds=ttl_seconds)
        self.active_harness = active_harness

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def extend(self, additional_seconds: float = 60.0) -> None:
        """Extend lease expiration to accommodate prolonged ReAct reasoning."""
        self.expires_at = max(self.expires_at, datetime.now(timezone.utc) + timedelta(seconds=additional_seconds))


class SymbolTurnLeaseManager:
    """
    Coordinates per-symbol execution leases and manages dynamic event coalescence.
    """

    def __init__(self):
        self._leases: Dict[str, SymbolLease] = {}
        self._lock = asyncio.Lock()

    def _normalize(self, symbol: str) -> str:
        return (symbol or "").upper().replace("/", "").replace("_", "").strip()

    async def acquire_lease(
        self,
        symbol: str,
        holder_id: str,
        ttl_seconds: float = 300.0,
        active_harness: Optional[Any] = None,
    ) -> bool:
        """
        Attempt to acquire an exclusive analysis lease for a symbol.
        Returns True if lease acquired; False if actively leased by another holder.
        """
        clean = self._normalize(symbol)
        if not clean:
            return False

        async with self._lock:
            existing = self._leases.get(clean)
            if existing is not None and not existing.is_expired and existing.holder_id != holder_id:
                logger.info(
                    f"[SymbolTurnLeaseManager] Lease on '{clean}' denied to '{holder_id}'; "
                    f"currently held by '{existing.holder_id}' (expires in {(existing.expires_at - datetime.now(timezone.utc)).total_seconds():.1f}s)."
                )
                return False

            self._leases[clean] = SymbolLease(
                symbol=clean,
                holder_id=holder_id,
                ttl_seconds=ttl_seconds,
                active_harness=active_harness,
            )
            logger.debug(f"[SymbolTurnLeaseManager] Lease on '{clean}' granted to '{holder_id}' (TTL: {ttl_seconds}s).")
            return True

    async def release_lease(self, symbol: str, holder_id: str) -> bool:
        """Release active lease if held by the requesting holder."""
        clean = self._normalize(symbol)
        async with self._lock:
            existing = self._leases.get(clean)
            if existing and (existing.holder_id == holder_id or existing.is_expired):
                del self._leases[clean]
                logger.debug(f"[SymbolTurnLeaseManager] Lease on '{clean}' released by '{holder_id}'.")
                return True
            return False

    async def coalesce_event(
        self,
        symbol: str,
        event_text: str,
        sender: str = "reactive_trigger",
    ) -> bool:
        """
        Check if an active analysis lease exists for the symbol and coalesce the event
        directly into the active harness's steering queue.
        Returns True if coalesced; False if no active lease exists (caller must run new analysis).
        """
        clean = self._normalize(symbol)
        async with self._lock:
            existing = self._leases.get(clean)
            if not existing or existing.is_expired:
                return False

            if existing.active_harness is not None and hasattr(existing.active_harness, "enqueue_steering"):
                existing.active_harness.enqueue_steering(
                    content=event_text,
                    sender=sender,
                    mode="immediate",
                )
                existing.extend(60.0)  # Add 60s to accommodate the additional directive
                logger.info(
                    f"[SymbolTurnLeaseManager] Coalesced reactive event from '{sender}' on '{clean}' "
                    f"into active analysis held by '{existing.holder_id}'."
                )
                return True
            return False

    async def is_symbol_leased(self, symbol: str) -> bool:
        """Check if symbol currently has an active, unexpired lease."""
        clean = self._normalize(symbol)
        async with self._lock:
            existing = self._leases.get(clean)
            return existing is not None and not existing.is_expired

    async def get_lease_holder(self, symbol: str) -> Optional[str]:
        """Retrieve current leaseholder ID for symbol if active."""
        clean = self._normalize(symbol)
        async with self._lock:
            existing = self._leases.get(clean)
            if existing and not existing.is_expired:
                return existing.holder_id
            return None

    @classmethod
    def get_instance(cls) -> "SymbolTurnLeaseManager":
        """Retrieve the global singleton instance."""
        return get_symbol_lease_manager()



# Global singleton instance
_GLOBAL_LEASE_MANAGER: Optional[SymbolTurnLeaseManager] = None


def get_symbol_lease_manager() -> SymbolTurnLeaseManager:
    """Get or initialize global SymbolTurnLeaseManager singleton."""
    global _GLOBAL_LEASE_MANAGER
    if _GLOBAL_LEASE_MANAGER is None:
        _GLOBAL_LEASE_MANAGER = SymbolTurnLeaseManager()
    return _GLOBAL_LEASE_MANAGER
