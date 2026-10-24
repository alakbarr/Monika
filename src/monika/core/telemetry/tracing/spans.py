# ==============================================================================
# File: logging_observability/tracing/spans.py
# ==============================================================================

from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from collections.abc import Generator

from monika.core.telemetry.tracing.context import (
    _current_cycle_id,
    _current_trace_id,
    generate_trace_id,
    set_trace_context,
)
from monika.core.telemetry.tracing.tracer import Span, get_tracer


@contextmanager
def cycle_span(cycle_id: str, symbols: list[str] | None = None, **attrs) -> Generator[Span, None, None]:
    """Root span for an 8h cycle or analysis session."""
    tracer = get_tracer()
    trace_id = generate_trace_id()
    token_trace = _current_trace_id.set(trace_id)
    token_cycle = _current_cycle_id.set(cycle_id)

    span_attrs = {"cycle_id": cycle_id, "symbols": symbols or [], **attrs}
    span = tracer.start_span(f"cycle:{cycle_id}", kind="cycle", attributes=span_attrs, trace_id=trace_id)
    try:
        with span:
            yield span
    finally:
        _current_trace_id.reset(token_trace)
        _current_cycle_id.reset(token_cycle)


@contextmanager
def node_span(node_name: str, cycle_id: str | None = None, **attrs) -> Generator[Span, None, None]:
    """Span for a LangGraph workflow node (e.g. fundamental, per_asset, debate, risk_gate)."""
    tracer = get_tracer()
    span_attrs = {"node_name": node_name, **attrs}
    token_cycle = None
    if cycle_id:
        span_attrs["cycle_id"] = cycle_id
        token_cycle = _current_cycle_id.set(cycle_id)
    span = tracer.start_span(f"node:{node_name}", kind="node", attributes=span_attrs)
    try:
        with span:
            yield span
    finally:
        if token_cycle is not None:
            _current_cycle_id.reset(token_cycle)


@contextmanager
def llm_span(provider: str, model: str, task_role: str | None = None, **attrs) -> Generator[Span, None, None]:
    """Span for an individual LLM invocation, tracking tokens, cost, and latency."""
    tracer = get_tracer()
    span_attrs = {
        "llm.provider": provider,
        "llm.model": model,
        "llm.task_role": task_role or "unknown",
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        **attrs,
    }
    span = tracer.start_span(f"llm:{task_role or model}", kind="llm", attributes=span_attrs)
    with span:
        yield span


@contextmanager
def tool_span(tool_name: str, symbol: str | None = None, **attrs) -> Generator[Span, None, None]:
    """Span for an individual tool execution."""
    tracer = get_tracer()
    span_attrs = {"tool.name": tool_name, "tool_name": tool_name, **attrs}
    if symbol:
        span_attrs["symbol"] = symbol
    span = tracer.start_span(f"tool:{tool_name}", kind="tool", attributes=span_attrs)
    with span:
        yield span


@contextmanager
def trade_span(
    symbol: str,
    action: str,
    ticket: int | None = None,
    lot_size: float | None = None,
    slippage_points: float | None = None,
    mae_points: float | None = None,
    mfe_points: float | None = None,
    **attrs,
) -> Generator[Span, None, None]:
    """Span for trade order execution and lifecycle tracking with slippage, MAE, and MFE."""
    tracer = get_tracer()
    span_attrs = {
        "symbol": symbol,
        "action": action,
        "ticket": ticket,
        "lot_size": lot_size,
        "slippage_points": slippage_points if slippage_points is not None else 0.0,
        "mae_points": mae_points if mae_points is not None else 0.0,
        "mfe_points": mfe_points if mfe_points is not None else 0.0,
        **attrs,
    }
    span = tracer.start_span(f"trade:{symbol}:{action}", kind="trade", attributes=span_attrs)
    with span:
        yield span
