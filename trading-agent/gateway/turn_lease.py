# ==============================================================================
# File: gateway/turn_lease.py
# ==============================================================================

"""
Conversation Turn Lease Manager & Concurrency Fence.
Guarantees mutually exclusive turn execution per chat/channel, preventing
race conditions and out-of-order responses from overlapping user messages.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("TradingAgent.Gateway.TurnLease")

DEFAULT_LEASE_TTL = 90.0  # seconds


@dataclass
class LeaseRecord:
    conversation_id: str
    holder_id: str
    acquired_at: float
    expires_at: float


class TurnLeaseManager:
    """
    Manages exclusive execution leases for conversation turns.
    """

    def __init__(self, default_ttl: float = DEFAULT_LEASE_TTL):
        self.default_ttl = default_ttl
        self._leases: Dict[str, LeaseRecord] = {}
        self._lock = asyncio.Lock()

    async def acquire_lease(
        self,
        conversation_id: str,
        holder_id: str,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        """
        Attempts to acquire an exclusive turn lease for a conversation.
        Returns True if acquired, False if currently held by another active turn.
        """
        ttl = ttl_seconds or self.default_ttl
        now = time.time()

        async with self._lock:
            existing = self._leases.get(conversation_id)
            if existing:
                if now < existing.expires_at and existing.holder_id != holder_id:
                    logger.debug(
                        f"[TurnLease] Lease rejected for '{conversation_id}': held by '{existing.holder_id}' (expires in {existing.expires_at - now:.1f}s)"
                    )
                    return False

            self._leases[conversation_id] = LeaseRecord(
                conversation_id=conversation_id,
                holder_id=holder_id,
                acquired_at=now,
                expires_at=now + ttl,
            )
            logger.debug(f"[TurnLease] Acquired lease for '{conversation_id}' by '{holder_id}' (TTL: {ttl}s)")
            return True

    async def renew_lease(
        self,
        conversation_id: str,
        holder_id: str,
        extension_seconds: float = 30.0,
    ) -> bool:
        """Extends lease expiration for a long-running turn."""
        now = time.time()
        async with self._lock:
            existing = self._leases.get(conversation_id)
            if not existing or existing.holder_id != holder_id:
                return False

            existing.expires_at = max(existing.expires_at, now) + extension_seconds
            logger.debug(f"[TurnLease] Renewed lease for '{conversation_id}' (+{extension_seconds}s)")
            return True

    async def release_lease(self, conversation_id: str, holder_id: str) -> bool:
        """Releases the turn lease if held by the caller."""
        async with self._lock:
            existing = self._leases.get(conversation_id)
            if existing and existing.holder_id == holder_id:
                del self._leases[conversation_id]
                logger.debug(f"[TurnLease] Released lease for '{conversation_id}' by '{holder_id}'")
                return True
            return False

    async def is_lease_active(self, conversation_id: str) -> bool:
        """Checks if a valid, unexpired lease exists for a conversation."""
        now = time.time()
        async with self._lock:
            existing = self._leases.get(conversation_id)
            if existing and now < existing.expires_at:
                return True
            if existing and now >= existing.expires_at:
                del self._leases[conversation_id]
            return False
