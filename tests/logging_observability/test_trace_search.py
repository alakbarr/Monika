import pytest
from logging_observability.tracing.exporters import InMemoryTraceStore, TraceRecord


@pytest.fixture
def store_with_spans():
    store = InMemoryTraceStore(capacity=100)
    # Span 1: Fast OK LLM
    store.record_span(TraceRecord(
        trace_id="t1", span_id="s1", parent_span_id=None,
        name="llm_fast", kind="llm", start_time="2026-09-15T00:00:00Z",
        duration_ms=500.0, status="OK",
        attributes={"llm.provider": "groq", "llm.model": "qwen-2.5", "input_tokens": 100, "output_tokens": 50},
    ))
    # Span 2: Slow OK LLM
    store.record_span(TraceRecord(
        trace_id="t2", span_id="s2", parent_span_id=None,
        name="llm_slow", kind="llm", start_time="2026-09-15T00:01:00Z",
        duration_ms=18000.0, status="OK",
        attributes={"llm.provider": "openrouter", "llm.model": "claude-3-7-sonnet", "input_tokens": 5000, "output_tokens": 1200},
    ))
    # Span 3: Failed LLM
    store.record_span(TraceRecord(
        trace_id="t3", span_id="s3", parent_span_id=None,
        name="llm_error", kind="llm", start_time="2026-09-15T00:02:00Z",
        duration_ms=1200.0, status="ERROR", error="RateLimitError: 429",
        attributes={"llm.provider": "gemini", "llm.model": "gemini-2.5-flash"},
    ))
    # Span 4: Tool call
    store.record_span(TraceRecord(
        trace_id="t4", span_id="s4", parent_span_id=None,
        name="tool_indicator", kind="tool", start_time="2026-09-15T00:03:00Z",
        duration_ms=50.0, status="OK",
    ))
    return store


def test_search_by_kind(store_with_spans):
    llm_spans = store_with_spans.search_spans(kind="llm")
    assert len(llm_spans) == 3
    tool_spans = store_with_spans.search_spans(kind="tool")
    assert len(tool_spans) == 1


def test_search_by_duration(store_with_spans):
    slow_spans = store_with_spans.search_spans(min_duration_ms=10000.0)
    assert len(slow_spans) == 1
    assert slow_spans[0].name == "llm_slow"


def test_search_by_status(store_with_spans):
    err_spans = store_with_spans.search_spans(status="ERROR")
    assert len(err_spans) == 1
    assert err_spans[0].error == "RateLimitError: 429"


def test_search_by_provider(store_with_spans):
    gemini_spans = store_with_spans.search_spans(provider="gemini")
    assert len(gemini_spans) == 1
    assert gemini_spans[0].name == "llm_error"


def test_search_by_model(store_with_spans):
    claude_spans = store_with_spans.search_spans(model="claude")
    assert len(claude_spans) == 1
    assert claude_spans[0].name == "llm_slow"
