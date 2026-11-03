# ==============================================================================
# File: core/telemetry/batched_sink.py
# Description: Dual-lane asynchronous batched telemetry sink for high-throughput persistence.
# ==============================================================================

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, UTC
from typing import Any, List, Optional

logger = logging.getLogger("TradingAgent.BatchedTelemetrySink")

CRITICAL_CATEGORIES = frozenset({"trading", "risk"})


@dataclass
class _QueuedActivity:
    timestamp: datetime
    category: str
    description: str
    related_id: Optional[int]
    actor: str


class BatchedTelemetrySink:
    """
    High-performance batched telemetry sink implementing TelemetrySink.

    Dual-lane persistence:
    1. Critical lane (risk, trading, explicit session): Writes immediately and fails closed.
    2. Routine lane (scraping, system, analysis): Enqueued into in-memory bounded queue and
       flushed in micro-batches (e.g. every 2s or 50 items) to eliminate DB lock contention.
    """

    def __init__(
        self,
        flush_interval_seconds: float = 2.0,
        max_batch_size: int = 50,
        max_queue_size: int = 1000,
    ) -> None:
        self.flush_interval = flush_interval_seconds
        self.max_batch_size = max_batch_size
        self._queue: asyncio.Queue[_QueuedActivity] = asyncio.Queue(maxsize=max_queue_size)
        self._flusher_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._lock = asyncio.Lock()

    def start(self) -> None:
        """Start the background batch flusher task."""
        if not self._running:
            self._running = True
            self._flusher_task = asyncio.create_task(self._flusher_loop(), name="BatchedTelemetryFlusher")

    async def stop(self) -> None:
        """Gracefully stop and flush all queued telemetry."""
        self._running = False
        if self._flusher_task and not self._flusher_task.done():
            self._flusher_task.cancel()
            try:
                await self._flusher_task
            except asyncio.CancelledError:
                pass
        await self.flush()

    async def persist_activity(
        self,
        category: str,
        description: str,
        related_id: Optional[int] = None,
        actor: str = "system",
        session: Any = None,
    ) -> Optional[int]:
        """Dual-lane activity persistence."""
        from monika.infrastructure.database.models import ActivityLog

        now = datetime.now(UTC)
        cat = category.lower().strip()

        # Critical lane: persist immediately
        if cat in CRITICAL_CATEGORIES or session is not None:
            if session is not None:
                entry = ActivityLog(
                    timestamp=now,
                    category=cat,
                    description=description[:2000],
                    related_id=related_id,
                    actor=actor,
                )
                session.add(entry)
                await session.flush()
                return entry.id
            else:
                from monika.infrastructure.database.db import get_write_session

                async with get_write_session() as write_sess:
                    entry = ActivityLog(
                        timestamp=now,
                        category=cat,
                        description=description[:2000],
                        related_id=related_id,
                        actor=actor,
                    )
                    write_sess.add(entry)
                    await write_sess.flush()
                    return entry.id

        # Routine lane: enqueue for micro-batching
        item = _QueuedActivity(
            timestamp=now,
            category=cat,
            description=description[:2000],
            related_id=related_id,
            actor=actor,
        )
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            # Drop oldest entry on queue saturation to preserve memory bounded ceiling
            try:
                _ = self._queue.get_nowait()
                self._queue.put_nowait(item)
            except Exception:
                pass
        return None

    async def persist_spans(self, spans: list[Any]) -> None:
        """Persist evicted tracing spans."""
        # Spans can be persisted to trace table if configured
        pass

    async def flush(self) -> int:
        """Flush all pending activities to database in a single transaction."""
        items: List[_QueuedActivity] = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not items:
            return 0

        from monika.infrastructure.database.db import get_write_session
        from monika.infrastructure.database.models import ActivityLog

        count = len(items)
        try:
            async with get_write_session() as sess:
                entries = [
                    ActivityLog(
                        timestamp=item.timestamp,
                        category=item.category,
                        description=item.description,
                        related_id=item.related_id,
                        actor=item.actor,
                    )
                    for item in items
                ]
                sess.add_all(entries)
                await sess.flush()
            logger.debug(f"[BatchedTelemetrySink] Flushed {count} activity log entries")
            return count
        except Exception as e:
            logger.warning(f"[BatchedTelemetrySink] Batch flush failed: {e}")
            return 0

    async def _flusher_loop(self) -> None:
        """Background loop flushing batches periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[BatchedTelemetrySink] Error in flusher loop: {e}")


_GLOBAL_BATCHED_SINK: Optional[BatchedTelemetrySink] = None


def enable_batched_telemetry(flush_interval_seconds: float = 2.0) -> BatchedTelemetrySink:
    """Enable global batched telemetry sink for high-throughput non-stop operation."""
    global _GLOBAL_BATCHED_SINK
    if _GLOBAL_BATCHED_SINK is None:
        from monika.core.telemetry.sinks import set_telemetry_sink

        _GLOBAL_BATCHED_SINK = BatchedTelemetrySink(flush_interval_seconds=flush_interval_seconds)
        _GLOBAL_BATCHED_SINK.start()
        set_telemetry_sink(_GLOBAL_BATCHED_SINK)
    return _GLOBAL_BATCHED_SINK


async def disable_batched_telemetry() -> None:
    """Disable and flush global batched telemetry sink."""
    global _GLOBAL_BATCHED_SINK
    if _GLOBAL_BATCHED_SINK is not None:
        from monika.core.telemetry.sinks import set_telemetry_sink

        await _GLOBAL_BATCHED_SINK.stop()
        set_telemetry_sink(None)
        _GLOBAL_BATCHED_SINK = None
