# ==============================================================================
# File: tests/utils/test_context_tracker.py
# Description: Unit Tests for ContextTracker & Token Accumulator (Q5)
# ==============================================================================

import pytest
from utils.llm.context_tracker import ContextTracker, get_context_tracker


def test_context_tracker_initial_state():
    tracker = ContextTracker(default_model="claude-3-5-sonnet")
    assert tracker.max_context_window == 200000
    assert tracker.get_used_tokens() == 0
    assert tracker.get_utilization_ratio() == 0.0
    assert tracker.get_cache_hit_rate() == 0.0


def test_context_tracker_record_usage():
    tracker = ContextTracker(default_model="claude-3-5-sonnet")
    tracker.record_usage(input_tokens=10000, output_tokens=2000, cached_tokens=5000, step="stage1")

    assert tracker.input_tokens == 10000
    assert tracker.output_tokens == 2000
    assert tracker.cached_tokens == 5000
    assert tracker.get_used_tokens() == 12000
    # 12,000 / 200,000 = 0.06
    assert pytest.approx(tracker.get_utilization_ratio(), 0.001) == 0.06
    # 5,000 / 15,000 = 33.33%
    assert pytest.approx(tracker.get_cache_hit_rate(), 0.1) == 33.33
    assert not tracker.is_approaching_limit(0.8)


def test_context_tracker_approaching_limit():
    tracker = ContextTracker(default_model="claude-3-5-sonnet")
    tracker.record_usage(input_tokens=150000, output_tokens=20000)
    # 170,000 / 200,000 = 85%
    assert tracker.is_approaching_limit(0.8)
    assert not tracker.is_approaching_limit(0.9)


def test_context_tracker_reset_and_summary():
    tracker = ContextTracker(default_model="gemini-3.7-flash")
    # Gemini 3.7 Flash context window is 1M (1,048,576)
    assert tracker.max_context_window == 1048576

    tracker.record_usage(50000, 10000, cached_tokens=20000, step="debate")
    summary = tracker.get_summary()
    assert summary["model"] == "gemini-3.7-flash"
    assert summary["used_tokens"] == 60000
    assert summary["span_count"] == 1

    tracker.reset(cycle_id="cycle_99", model="claude-3-5-sonnet")
    assert tracker.current_cycle_id == "cycle_99"
    assert tracker.get_used_tokens() == 0
    assert len(tracker.spans) == 0
    assert tracker.max_context_window == 200000


def test_global_singleton():
    t1 = get_context_tracker()
    t2 = get_context_tracker()
    assert t1 is t2
