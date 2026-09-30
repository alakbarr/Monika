import pytest
import time
from utils.llm.cache_miss_detector import CacheMissDetector, CacheMissReport


def test_first_call_not_miss():
    detector = CacheMissDetector()
    report = detector.check(cached_tokens=1000, model="claude-3-7-sonnet", input_tokens=1500)
    assert report.missed is False
    assert report.reason == "first_call"
    assert report.missed_cost_usd == 0.0


def test_cache_hit_not_miss():
    detector = CacheMissDetector()
    detector.check(cached_tokens=1000, model="claude-3-7-sonnet", input_tokens=1500)
    # Subsequent turn with cache hit
    report = detector.check(cached_tokens=1200, model="claude-3-7-sonnet", input_tokens=1700)
    assert report.missed is False
    assert report.reason == "none"


def test_cache_miss_model_changed():
    detector = CacheMissDetector()
    detector.check(cached_tokens=2000, model="claude-3-7-sonnet", input_tokens=2500)
    # Switched to different model and got 0 cached tokens
    report = detector.check(cached_tokens=0, model="gemini-2.5-flash", input_tokens=2500)
    assert report.missed is True
    assert report.reason == "model_changed"
    assert report.missed_cost_usd > 0.0
    assert report.prev_cached_tokens == 2000


def test_cache_miss_ttl_expired():
    # Cache TTL = 100ms for testing
    detector = CacheMissDetector(cache_ttl_ms=50.0)
    detector.check(cached_tokens=2000, model="claude-3-7-sonnet", input_tokens=2500)
    time.sleep(0.08)  # Wait > 50ms
    report = detector.check(cached_tokens=0, model="claude-3-7-sonnet", input_tokens=2500)
    assert report.missed is True
    assert report.reason == "ttl_expired"
    assert report.missed_cost_usd > 0.0


def test_cache_miss_summary_stats():
    detector = CacheMissDetector()
    detector.check(cached_tokens=1000, model="claude-3-7-sonnet")
    detector.check(cached_tokens=0, model="gemini-2.5-flash")  # 1 miss

    summary = detector.get_summary()
    assert summary["total_calls"] == 2
    assert summary["total_misses"] == 1
    assert summary["miss_rate"] == 0.5
    assert summary["total_missed_cost_usd"] > 0.0


def test_cache_miss_multi_context_isolation():
    detector = CacheMissDetector()
    # Task A turn 1 & 2
    rep_a1 = detector.check(cached_tokens=0, model="gemini-3.5-flash-lite", context_key="task_A")
    assert rep_a1.missed is False
    assert rep_a1.reason == "first_call"

    rep_a2 = detector.check(cached_tokens=12187, model="gemini-3.5-flash-lite", context_key="task_A")
    assert rep_a2.missed is False
    assert rep_a2.reason == "none"

    # Task B starts right after Task A had 12187 cached tokens
    # Must NOT be flagged as cache miss or prefix_changed
    rep_b1 = detector.check(cached_tokens=0, model="gemini-3.5-flash-lite", context_key="task_B")
    assert rep_b1.missed is False
    assert rep_b1.reason == "first_call"
    assert rep_b1.curr_cached_tokens == 0

    # Task A continues: hit against Task A's previous 12187
    rep_a3 = detector.check(cached_tokens=12500, model="gemini-3.5-flash-lite", context_key="task_A")
    assert rep_a3.missed is False
    assert rep_a3.prev_cached_tokens == 12187

    # Summary: 0 misses across both tasks
    summary = detector.get_summary()
    assert summary["total_calls"] == 4
    assert summary["total_misses"] == 0


def test_cache_miss_symbol_isolation_prevents_false_alarm():
    """Verify that EURUSD and GBPUSD calls under their respective symbol context keys do not trigger false miss."""
    detector = CacheMissDetector()
    
    # EURUSD call cached 3692 tokens
    rep_eur1 = detector.check(cached_tokens=3692, model="gemini-3.5-flash-lite", context_key="specialist:specialist_sentiment:EURUSD")
    assert rep_eur1.missed is False
    assert rep_eur1.reason == "first_call"

    # GBPUSD call has 0 cached tokens - should be treated as first_call, NOT prefix_changed
    rep_gbp1 = detector.check(cached_tokens=0, model="gemini-3.5-flash-lite", context_key="specialist:specialist_sentiment:GBPUSD")
    assert rep_gbp1.missed is False
    assert rep_gbp1.reason == "first_call"
    assert detector.get_summary()["total_misses"] == 0

