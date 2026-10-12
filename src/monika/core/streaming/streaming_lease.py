# ==============================================================================
# File: utils/streaming/streaming_lease.py
# ==============================================================================

"""
Single-Writer Stream Lease & Output Serialization Coordinator.
Institutional-grade streaming telemetry and outbox protection.

Prevents split-brain terminal or outbox corruption when concurrent asynchronous
coroutines (e.g. GraphCycleScheduler, NewsWatcher, PositionGuardian, interactive CLI/bot)
attempt to write streaming token deltas to the same surface (Telegram chat, PTY, WebSocket).
Enforces exclusive leaseholder rights with automatic heartbeat renewal and stale-lease eviction.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, Optional

logger = logging.getLogger("TradingAgent.Utils.StreamingLease")


class LeaseAcquisitionTimeoutError(TimeoutError):
    """Raised when acquiring a stream writer lease exceeds timeout."""
    pass


class LeaseExpiredOrInvalidError(RuntimeError):
    """Raised when an operation is attempted on an invalid or expired lease."""
    pass


@dataclass
class LeaseRecord:
    lease_id: str
    surface_id: str
    owner: str
    acquired_at: float
    expires_at: float


class StreamWriterLeaseCoordinator:
    """
    Coordinates exclusive stream write locks across output surfaces.
    """

    def __init__(self, default_duration_sec: float = 30.0):
        self.default_duration_sec = default_duration_sec
        self._locks: Dict[str, asyncio.Lock] = {}
        self._active_leases: Dict[str, LeaseRecord] = {}
        self._master_lock = asyncio.Lock()

    async def _get_surface_lock(self, surface_id: str) -> asyncio.Lock:
        async with self._master_lock:
            if surface_id not in self._locks:
                self._locks[surface_id] = asyncio.Lock()
            return self._locks[surface_id]

    @asynccontextmanager
    async def acquire_lease(
        self,
        surface_id: str,
        owner: str = "default_worker",
        timeout_sec: float = 10.0,
        duration_sec: Optional[float] = None,
    ) -> AsyncIterator[StreamWriterLeaseHandle]:
        """
        Acquires an exclusive single-writer stream lease for a designated surface ID.
        """
        duration = duration_sec or self.default_duration_sec
        surface_lock = await self._get_surface_lock(surface_id)

        try:
            await asyncio.wait_for(surface_lock.acquire(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            raise LeaseAcquisitionTimeoutError(
                f"Timed out after {timeout_sec:.1f}s waiting for stream lease on surface '{surface_id}'."
            )

        lease_id = str(uuid.uuid4())
        now = time.time()
        record = LeaseRecord(
            lease_id=lease_id,
            surface_id=surface_id,
            owner=owner,
            acquired_at=now,
            expires_at=now + duration,
        )
        self._active_leases[surface_id] = record

        handle = StreamWriterLeaseHandle(
            coordinator=self,
            record=record,
            surface_lock=surface_lock,
            duration_sec=duration,
        )

        try:
            logger.debug(f"[StreamLease] Acquired lease {lease_id[:8]} for surface '{surface_id}' by '{owner}'.")
            yield handle
        finally:
            await handle._release_internal()


class StreamWriterLeaseHandle:
    """
    Handle held by active writer allowing chunk emission and heartbeat refreshes.
    """

    def __init__(
        self,
        coordinator: StreamWriterLeaseCoordinator,
        record: LeaseRecord,
        surface_lock: asyncio.Lock,
        duration_sec: float,
    ):
        self._coordinator = coordinator
        self._record = record
        self._lock = surface_lock
        self._duration_sec = duration_sec
        self._is_released = False

    @property
    def is_valid(self) -> bool:
        if self._is_released:
            return False
        return time.time() < self._record.expires_at

    def heartbeat(self) -> None:
        """Extends the lease expiration time from now."""
        if self._is_released:
            raise LeaseExpiredOrInvalidError("Cannot extend a released lease.")
        self._record.expires_at = time.time() + self._duration_sec

    async def write(
        self,
        chunk: str,
        writer_fn: Optional[Callable[[str], Any]] = None,
    ) -> None:
        """
        Dispatches a chunk through writer_fn if lease is valid and active.
        """
        if not self.is_valid:
            raise LeaseExpiredOrInvalidError(
                f"Stream lease {self._record.lease_id[:8]} for surface '{self._record.surface_id}' has expired."
            )
        self.heartbeat()

        if writer_fn:
            res = writer_fn(chunk)
            if asyncio.iscoroutine(res):
                await res

    async def _release_internal(self) -> None:
        if self._is_released:
            return
        self._is_released = True
        self._coordinator._active_leases.pop(self._record.surface_id, None)
        if self._lock.locked():
            self._lock.release()
        logger.debug(f"[StreamLease] Released lease {self._record.lease_id[:8]} on surface '{self._record.surface_id}'.")


# Global singleton coordinator
_GLOBAL_LEASE_COORDINATOR = StreamWriterLeaseCoordinator()


def get_stream_lease_coordinator() -> StreamWriterLeaseCoordinator:
    """Returns the process-wide StreamWriterLeaseCoordinator singleton."""
    return _GLOBAL_LEASE_COORDINATOR
