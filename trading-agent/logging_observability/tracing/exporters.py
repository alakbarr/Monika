# ==============================================================================
# File: logging_observability/tracing/exporters.py
# ==============================================================================

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import json

logger = logging.getLogger("TradingAgent.Tracing.Exporters")


@dataclass
class TraceRecord:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    kind: str  # "cycle", "node", "llm", "tool"
    start_time: str
    end_time: Optional[str] = None
    duration_ms: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "OK"  # "OK", "ERROR"
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class InMemoryTraceStore:
    """Thread-safe ring buffer storing recent distributed traces for audit & dashboard with DB eviction persistence."""

    def __init__(self, capacity: int = 2000, evicted_flush_batch: int = 20):
        self._capacity = capacity
        self._spans: deque[TraceRecord] = deque(maxlen=capacity)
        self._evicted_buffer: List[TraceRecord] = []
        self._evicted_flush_batch = evicted_flush_batch

    def record_span(self, record: TraceRecord):
        if len(self._spans) >= self._capacity:
            evicted = self._spans.popleft()
            self._evicted_buffer.append(evicted)
            if len(self._evicted_buffer) >= self._evicted_flush_batch:
                self._schedule_eviction_flush()
        self._spans.append(record)

    def _schedule_eviction_flush(self):
        """Schedule asynchronous flush to database if event loop is running."""
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self.flush_evicted_to_db())
        except (RuntimeError, AttributeError):
            pass

    async def flush_evicted_to_db(self) -> int:
        """Persist evicted spans to TradingEvent / ActivityLog in database."""
        if not self._evicted_buffer:
            return 0
        to_flush = list(self._evicted_buffer)
        self._evicted_buffer.clear()
        try:
            from database.db import get_session
            from database.models import TradingEvent
            import uuid
            count = 0
            async with get_session() as session:
                for span in to_flush:
                    event = TradingEvent(
                        id=str(uuid.uuid4()),
                        event_type="trace.span_evicted",
                        correlation_id=span.trace_id,
                        causation_id=span.parent_span_id,
                        payload=span.to_dict(),
                        actor="trace_store",
                        ts_created=datetime.now(timezone.utc),
                    )
                    session.add(event)
                    count += 1
                await session.commit()
            logger.debug(f"[TraceStore] Persisted {count} evicted trace spans to DB.")
            return count
        except Exception as e:
            logger.debug(f"[TraceStore] Could not persist evicted spans to DB: {e}")
            # Re-buffer in case of transient DB failure (capped to avoid memory leak)
            if len(self._evicted_buffer) < 500:
                self._evicted_buffer.extend(to_flush)
            return 0


    def search_spans(
        self,
        kind: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 50,
    ) -> List[TraceRecord]:
        """Search in-memory spans with performance and error filters (newest first)."""
        results = []
        for span in reversed(self._spans):
            if kind and span.kind != kind:
                continue
            if min_duration_ms is not None and span.duration_ms < min_duration_ms:
                continue
            if status and span.status.upper() != status.upper():
                continue
            if provider:
                span_prov = str(span.attributes.get("llm.provider") or span.attributes.get("provider") or "").lower()
                if provider.lower() not in span_prov:
                    continue
            if model:
                span_model = str(span.attributes.get("llm.model") or span.attributes.get("model") or "").lower()
                if model.lower() not in span_model:
                    continue
            results.append(span)
            if len(results) >= limit:
                break
        return results

    def get_spans(
        self,
        limit: int = 100,
        trace_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[dict]:
        """Filter spans by criteria and return as dicts (newest first)."""
        results = []
        for span in reversed(self._spans):
            if trace_id and span.trace_id != trace_id:
                continue
            if cycle_id and span.attributes.get("cycle_id") != cycle_id:
                continue
            if kind and span.kind != kind:
                continue
            results.append(span.to_dict())
            if len(results) >= limit:
                break
        return results

    def get_trace_tree(self, trace_id: str) -> List[dict]:
        """Reconstruct hierarchical call tree for a given trace_id."""
        matching = [s.to_dict() for s in self._spans if s.trace_id == trace_id]
        if not matching:
            return []

        # Index by span_id
        span_map = {s["span_id"]: s for s in matching}
        for s in span_map.values():
            s["children"] = []

        roots = []
        for s in span_map.values():
            parent_id = s.get("parent_span_id")
            if parent_id and parent_id in span_map:
                span_map[parent_id]["children"].append(s)
            else:
                roots.append(s)
        return roots

    def get_cycle_summary(self, cycle_id: str) -> dict:
        """Aggregate total token usage, USD cost, tool calls, and node timings for a cycle."""
        matching = [s for s in self._spans if s.attributes.get("cycle_id") == cycle_id]
        total_in_tokens = 0
        total_out_tokens = 0
        total_cost_usd = 0.0
        tool_counts: Dict[str, int] = {}
        node_durations: Dict[str, float] = {}

        for s in matching:
            if s.kind == "llm":
                total_in_tokens += s.attributes.get("input_tokens", 0)
                total_out_tokens += s.attributes.get("output_tokens", 0)
                total_cost_usd += s.attributes.get("cost_usd", 0.0)
            elif s.kind == "tool":
                tool_name = s.attributes.get("tool_name", s.name)
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            elif s.kind == "node":
                node_durations[s.name] = s.duration_ms

        return {
            "cycle_id": cycle_id,
            "total_spans": len(matching),
            "total_input_tokens": total_in_tokens,
            "total_output_tokens": total_out_tokens,
            "total_cost_usd": round(total_cost_usd, 6),
            "tool_call_counts": tool_counts,
            "node_durations_ms": node_durations,
        }


# Global in-memory trace store
global_trace_store = InMemoryTraceStore()
