"""
Trace Search API — enables querying LLM performance and errors across cycles.
Solves gap: querying slow or failed LLM calls with granular filters.
"""
import logging
from fastapi import APIRouter, Query
from typing import Optional
from logging_observability.tracing.exporters import global_trace_store

logger = logging.getLogger("TradingAgent.Dashboard.TraceSearch")

trace_search_router = APIRouter(prefix="/api/traces", tags=["trace-search"])


@trace_search_router.get("/search")
async def search_traces(
    kind: Optional[str] = Query(None, description="Span kind: llm, tool, node, cycle"),
    min_duration_ms: Optional[float] = Query(None, description="Minimum duration in ms"),
    status: Optional[str] = Query(None, description="OK or ERROR"),
    provider: Optional[str] = Query(None, description="LLM provider name"),
    model: Optional[str] = Query(None, description="Model name"),
    limit: int = Query(50, le=200),
):
    """Search trace spans with performance and error filters."""
    spans = global_trace_store.search_spans(
        kind=kind,
        min_duration_ms=min_duration_ms,
        status=status,
        provider=provider,
        model=model,
        limit=limit,
    )
    return {
        "count": len(spans),
        "spans": [s.to_dict() for s in spans],
    }


@trace_search_router.get("/slow-llm")
async def slow_llm_calls(
    threshold_ms: float = Query(15000.0, description="Duration threshold in ms"),
    limit: int = Query(20, le=100),
):
    """Shortcut: find LLM calls slower than threshold."""
    spans = global_trace_store.search_spans(
        kind="llm",
        min_duration_ms=threshold_ms,
        limit=limit,
    )
    return {
        "threshold_ms": threshold_ms,
        "count": len(spans),
        "spans": [
            {
                "name": s.name,
                "provider": s.attributes.get("llm.provider") or s.attributes.get("provider"),
                "model": s.attributes.get("llm.model") or s.attributes.get("model"),
                "duration_ms": round(s.duration_ms, 1),
                "input_tokens": s.attributes.get("input_tokens"),
                "output_tokens": s.attributes.get("output_tokens"),
                "cost_usd": s.attributes.get("cost_usd"),
                "cycle_id": s.attributes.get("cycle_id"),
                "status": s.status,
                "error": s.error,
                "start_time": s.start_time,
            }
            for s in spans
        ],
    }
