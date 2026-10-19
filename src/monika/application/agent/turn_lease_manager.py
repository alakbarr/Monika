"""
File: trading-agent/agent/turn_lease_manager.py

Symbol Turn Lease & Event Coalescence Manager.
Prevents concurrent analysis collisions across schedulers on identical asset symbols.
Automatically coalesces reactive market shocks and breaking news directly into the
active analysis turn's steering queue without restarting the analysis cycle.
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
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

    _instance: Optional["SymbolTurnLeaseManager"] = None
    _init_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SymbolTurnLeaseManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._init_lock:
            cls._instance = None

    def __init__(self):
        self._leases: Dict[str, SymbolLease] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _prune_expired_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._leases.items() if v.expires_at <= now]
        for k in expired:
            del self._leases[k]

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

        async with self._get_lock():
            self._prune_expired_locked()
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

    async def attach_harness_for_symbol(self, symbol: str, harness: Any) -> bool:
        """Attach active harness to existing unexpired lease for symbol."""
        clean = self._normalize(symbol)
        async with self._get_lock():
            existing = self._leases.get(clean)
            if existing and not existing.is_expired:
                existing.active_harness = harness
                logger.debug(f"[SymbolTurnLeaseManager] Attached active harness to '{clean}'.")
                return True
            return False

    async def attach_harness(self, symbol: str, holder_id: str, harness: Any) -> bool:
        """Attach active harness to an existing unexpired lease."""
        clean = self._normalize(symbol)
        async with self._get_lock():
            existing = self._leases.get(clean)
            if existing and not existing.is_expired and existing.holder_id == holder_id:
                existing.active_harness = harness
                logger.debug(f"[SymbolTurnLeaseManager] Attached active harness to '{clean}' for '{holder_id}'.")
                return True
            return False

    async def release_lease(self, symbol: str, holder_id: str) -> bool:
        """Release active lease if held by the requesting holder."""
        clean = self._normalize(symbol)
        async with self._get_lock():
            self._prune_expired_locked()
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
        async with self._get_lock():
            self._prune_expired_locked()
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
        async with self._get_lock():
            self._prune_expired_locked()
            existing = self._leases.get(clean)
            return existing is not None and not existing.is_expired

    async def get_lease_holder(self, symbol: str) -> Optional[str]:
        """Retrieve current leaseholder ID for symbol if active."""
        clean = self._normalize(symbol)
        async with self._get_lock():
            self._prune_expired_locked()
            existing = self._leases.get(clean)
            if existing and not existing.is_expired:
                return existing.holder_id
            return None


def get_symbol_lease_manager() -> SymbolTurnLeaseManager:
    """Get or initialize global SymbolTurnLeaseManager singleton."""
    return SymbolTurnLeaseManager.get_instance()


# Canonical aliases
TurnLeaseManager = SymbolTurnLeaseManager
get_turn_lease_manager = get_symbol_lease_manager

__all__ = [
    "SymbolLease",
    "SymbolTurnLeaseManager",
    "TurnLeaseManager",
    "get_symbol_lease_manager",
    "get_turn_lease_manager",
]
