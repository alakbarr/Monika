# ==============================================================================
# File: logging_observability/tracing/tracer.py
# ==============================================================================

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from logging_observability.tracing.context import (
    generate_id,
    generate_trace_id,
    get_current_trace_id,
    get_current_span_id,
    get_current_cycle_id,
    _current_span_id,
    _current_trace_id,
    _current_cycle_id,
)
from logging_observability.tracing.exporters import (
    TraceRecord,
    global_trace_store,
)

logger = logging.getLogger("TradingAgent.Tracer")


class Span:
    """Represents a single distributed trace span."""

    def __init__(
        self,
        name: str,
        kind: str = "internal",
        parent_span_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.kind = kind
        self.span_id = generate_id()
        self.trace_id = trace_id or get_current_trace_id()
        self.parent_span_id = parent_span_id or get_current_span_id()
        self.attributes: Dict[str, Any] = attributes or {}
        
        cycle_id = get_current_cycle_id()
        if cycle_id and "cycle_id" not in self.attributes:
            self.attributes["cycle_id"] = cycle_id

        self.start_time = datetime.now(timezone.utc)
        self._start_perf = time.perf_counter()
        self.end_time: Optional[datetime] = None
        self.duration_ms: float = 0.0
        self.status = "OK"
        self.error: Optional[str] = None
        self._token_span_id = None

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def set_attributes(self, attrs: Dict[str, Any]):
        self.attributes.update(attrs)

    def set_status(self, status: str, error: Optional[str] = None):
        self.status = status
        if error:
            self.error = error

    def record_exception(self, e: Exception):
        self.status = "ERROR"
        self.error = f"{type(e).__name__}: {str(e)}"
        self.set_attribute("exception.type", type(e).__name__)
        self.set_attribute("exception.message", str(e))

    def end(self):
        if self.end_time is not None:
            return
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (time.perf_counter() - self._start_perf) * 1000.0

        record = TraceRecord(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            kind=self.kind,
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat(),
            duration_ms=round(self.duration_ms, 2),
            attributes=dict(self.attributes),
            status=self.status,
            error=self.error,
        )
        global_trace_store.record_span(record)

    def __enter__(self):
        self._token_span_id = _current_span_id.set(self.span_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.record_exception(exc_val)
        self.end()
        if self._token_span_id:
            _current_span_id.reset(self._token_span_id)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


class AgentTracer:
    """Tracer service providing OpenInference / OpenTelemetry compatible spans."""

    def __init__(self):
        self._otel_tracer = None
        self._init_otel()

    def _init_otel(self):
        try:
            from opentelemetry import trace  # type: ignore
            self._otel_tracer = trace.get_tracer("tradeagent.ai")
        except ImportError:
            self._otel_tracer = None

    def start_span(
        self,
        name: str,
        kind: str = "internal",
        attributes: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Span:
        return Span(
            name=name,
            kind=kind,
            parent_span_id=parent_span_id,
            trace_id=trace_id,
            attributes=attributes,
        )


_default_tracer = AgentTracer()


def get_tracer() -> AgentTracer:
    return _default_tracer
