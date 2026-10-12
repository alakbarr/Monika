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
        self._events: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def acquire_lease(
        self,
        conversation_id: str,
        holder_id: str,
        ttl_seconds: Optional[float] = None,
        wait_timeout: float = 0.0,
    ) -> bool:
        """
        Attempts to acquire an exclusive turn lease for a conversation.
        If held by another active turn and wait_timeout > 0, waits up to wait_timeout
        seconds for the lease to be released before returning False.
        Returns True if acquired, False otherwise.
        """
        ttl = ttl_seconds or self.default_ttl
        deadline = time.time() + max(wait_timeout, 0.0)

        while True:
            now = time.time()
            event_to_wait: Optional[asyncio.Event] = None
            async with self._lock:
                existing = self._leases.get(conversation_id)
                if existing:
                    if now < existing.expires_at and existing.holder_id != holder_id:
                        if now >= deadline:
                            logger.debug(
                                f"[TurnLease] Lease rejected for '{conversation_id}': held by '{existing.holder_id}' (expires in {existing.expires_at - now:.1f}s)"
                            )
                            return False
                        # Prepare event to wait
                        if conversation_id not in self._events:
                            self._events[conversation_id] = asyncio.Event()
                        event_to_wait = self._events[conversation_id]
                    else:
                        # Existing lease expired or held by same holder -> free to reacquire
                        pass

                if event_to_wait is None:
                    self._leases[conversation_id] = LeaseRecord(
                        conversation_id=conversation_id,
                        holder_id=holder_id,
                        acquired_at=now,
                        expires_at=now + ttl,
                    )
                    logger.debug(f"[TurnLease] Acquired lease for '{conversation_id}' by '{holder_id}' (TTL: {ttl}s)")
                    return True

            rem = max(deadline - time.time(), 0.01)
            try:
                await asyncio.wait_for(event_to_wait.wait(), timeout=rem)
            except (asyncio.TimeoutError, TimeoutError):
                pass

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
        """Releases the turn lease if held by the caller and notifies waiting turns."""
        event_to_notify: Optional[asyncio.Event] = None
        async with self._lock:
            existing = self._leases.get(conversation_id)
            if existing and existing.holder_id == holder_id:
                del self._leases[conversation_id]
                event_to_notify = self._events.pop(conversation_id, None)
                logger.debug(f"[TurnLease] Released lease for '{conversation_id}' by '{holder_id}'")
            else:
                return False

        if event_to_notify:
            event_to_notify.set()
        return True

    async def is_lease_active(self, conversation_id: str) -> bool:
        """Checks if a valid, unexpired lease exists for a conversation."""
        now = time.time()
        async with self._lock:
            existing = self._leases.get(conversation_id)
            if existing and now < existing.expires_at:
                return True
            if existing and now >= existing.expires_at:
                del self._leases[conversation_id]
                ev = self._events.pop(conversation_id, None)
                if ev:
                    ev.set()
            return False
