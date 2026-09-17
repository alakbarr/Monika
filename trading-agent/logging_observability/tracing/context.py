# ==============================================================================
# File: logging_observability/tracing/context.py
# ==============================================================================

import contextvars
import uuid
from typing import Any, Dict, Optional

# Context variables for distributed tracing across async tasks
_current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_trace_id", default=None)
_current_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_span_id", default=None)
_current_cycle_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_cycle_id", default=None)
_trace_baggage: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("trace_baggage", default={})


def generate_id() -> str:
    """Generate a clean 16-hex character ID conforming to W3C TraceContext standards."""
    return uuid.uuid4().hex[:16]


def generate_trace_id() -> str:
    """Generate a 32-hex character Trace ID conforming to W3C TraceContext standards."""
    return uuid.uuid4().hex


def get_current_trace_id() -> str:
    tid = _current_trace_id.get()
    if not tid:
        tid = generate_trace_id()
        _current_trace_id.set(tid)
    return tid


def get_current_span_id() -> Optional[str]:
    return _current_span_id.get()


def get_current_cycle_id() -> Optional[str]:
    return _current_cycle_id.get()


def set_trace_context(trace_id: Optional[str] = None, span_id: Optional[str] = None, cycle_id: Optional[str] = None):
    if trace_id:
        _current_trace_id.set(trace_id)
    if span_id:
        _current_span_id.set(span_id)
    if cycle_id:
        _current_cycle_id.set(cycle_id)


def get_baggage(key: str, default: Any = None) -> Any:
    return _trace_baggage.get().get(key, default)


def set_baggage(key: str, value: Any):
    baggage = dict(_trace_baggage.get())
    baggage[key] = value
    _trace_baggage.set(baggage)
