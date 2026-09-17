# ==============================================================================
# File: tests/logging_observability/test_tracing.py
# ==============================================================================

import pytest
from logging_observability.tracing import (
    cycle_span,
    node_span,
    llm_span,
    tool_span,
    global_trace_store,
    get_current_trace_id,
    get_current_cycle_id,
)


def test_trace_spans_and_hierarchy():
    """Verify cycle, node, llm, and tool spans create proper hierarchy in trace store."""
    cycle_id = "test_cycle_001"

    with cycle_span(cycle_id=cycle_id, symbols=["EURUSD", "GBPUSD"]) as c_span:
        active_cycle_id = get_current_cycle_id()
        assert active_cycle_id == cycle_id
        trace_id = c_span.trace_id

        with node_span("fundamental_analysis", cycle_id=cycle_id) as n_span:
            assert n_span.attributes["node_name"] == "fundamental_analysis"
            assert n_span.parent_span_id == c_span.span_id

            with llm_span(provider="anthropic", model="claude-3-5-sonnet", task_role="fundamental_analyst") as l_span:
                l_span.set_attribute("input_tokens", 1200)
                l_span.set_attribute("output_tokens", 350)
                l_span.set_attribute("cost_usd", 0.00885)
                assert l_span.parent_span_id == n_span.span_id

            with tool_span("get_bond_yield_spreads", symbol="EURUSD") as t_span:
                assert t_span.parent_span_id == n_span.span_id

    # Verify spans in store
    spans = global_trace_store.get_spans(trace_id=trace_id)
    assert len(spans) >= 4

    # Verify cycle summary aggregation
    summary = global_trace_store.get_cycle_summary(cycle_id)
    assert summary["cycle_id"] == cycle_id
    assert summary["total_input_tokens"] == 1200
    assert summary["total_output_tokens"] == 350
    assert summary["total_cost_usd"] == 0.00885
    assert summary["tool_call_counts"].get("get_bond_yield_spreads") == 1

    # Verify tree reconstruction
    tree = global_trace_store.get_trace_tree(trace_id)
    assert len(tree) >= 1
    root = tree[0]
    assert root["kind"] == "cycle"
    assert len(root["children"]) >= 1
    assert root["children"][0]["kind"] == "node"


def test_span_context_manager_protocols_and_typing():
    """Verify that span helpers implement context manager protocol and proper generator typing."""
    import typing
    from logging_observability.tracing.tracer import Span

    # Check return type annotations
    for fn in (cycle_span, node_span, llm_span, tool_span):
        hints = typing.get_type_hints(fn)
        assert "return" in hints
        # Verify it conforms to Generator[Span, None, None]
        ret = hints["return"]
        assert getattr(ret, "__origin__", None) is typing.Generator or "Generator" in str(ret)

    # Check runtime context manager behavior
    cm = llm_span(provider="gemini", model="gemini-2.5-flash", task_role="test_role")
    assert hasattr(cm, "__enter__")
    assert hasattr(cm, "__exit__")
    with cm as span_obj:
        assert isinstance(span_obj, Span)
        assert span_obj.attributes["llm.provider"] == "gemini"
        assert span_obj.attributes["llm.model"] == "gemini-2.5-flash"

