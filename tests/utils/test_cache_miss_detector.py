import pytest
import time
from monika.infrastructure.llm.cache_miss_detector import CacheMissDetector, CacheMissReport


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
    rep_eur1 = detector.check(
        cached_tokens=3692, model="gemini-3.5-flash-lite", context_key="specialist:specialist_sentiment:EURUSD"
    )
    assert rep_eur1.missed is False
    assert rep_eur1.reason == "first_call"

    # GBPUSD call has 0 cached tokens - should be treated as first_call, NOT prefix_changed
    rep_gbp1 = detector.check(
        cached_tokens=0, model="gemini-3.5-flash-lite", context_key="specialist:specialist_sentiment:GBPUSD"
    )
    assert rep_gbp1.missed is False
    assert rep_gbp1.reason == "first_call"
    assert detector.get_summary()["total_misses"] == 0


def test_cache_miss_provider_cache_drop_with_identical_prefix_hash():
    """Verify that if prefix_hash matches the previous turn, the drop is classified as PROVIDER_EVICTED_OR_ROUTED."""
    detector = CacheMissDetector()

    # Turn 1: Cache written
    rep1 = detector.check(
        cached_tokens=5888,
        model="minimax/minimax-m3.1-flash",
        context_key="stage2:stage2_adjudicator:minimax/minimax-m3.1-flash:AUDUSD",
        prefix_hash="hash_prefix_stable_123",
    )
    assert rep1.missed is False
    assert rep1.reason == "first_call"

    # Turn 2: Provider drops cache / routes to cold node, but prefix hash is identical
    rep2 = detector.check(
        cached_tokens=0,
        model="minimax/minimax-m3.1-flash",
        context_key="stage2:stage2_adjudicator:minimax/minimax-m3.1-flash:AUDUSD",
        prefix_hash="hash_prefix_stable_123",
    )
    assert rep2.missed is True
    assert rep2.reason == "provider_cache_drop"
    assert rep2.root_cause == "PROVIDER_EVICTED_OR_ROUTED"
    assert rep2.prev_cached_tokens == 5888
    assert rep2.curr_cached_tokens == 0


def test_cache_miss_genuine_prefix_mutation_detected():
    """Verify that if prefix_hash actually mutates, the detector correctly flags PREFIX_MUTATED."""
    detector = CacheMissDetector()

    # Turn 1: Cache written with prompt A
    rep1 = detector.check(
        cached_tokens=5888,
        model="minimax/minimax-m3.1-flash",
        context_key="test_context",
        prefix_hash="hash_version_1",
    )
    assert rep1.missed is False

    # Turn 2: Prompt was modified (new system prompt), resulting in prefix_hash mutation
    rep2 = detector.check(
        cached_tokens=0,
        model="minimax/minimax-m3.1-flash",
        context_key="test_context",
        prefix_hash="hash_version_2",
    )
    assert rep2.missed is True
    assert rep2.reason == "prefix_changed"
    assert rep2.root_cause == "PREFIX_MUTATED"


def test_cache_miss_adjudication_cross_symbol_isolation():
    """Verify production scenario: AUDUSD followed by XBRUSD are isolated and do not trigger false PREFIX_MUTATED."""
    detector = CacheMissDetector()

    # Call 1: AUDUSD adjudication with 5888 cached tokens
    rep_aud = detector.check(
        cached_tokens=5888,
        model="minimax/minimax-m3.1-flash",
        context_key="stage2:stage2_adjudicator:minimax/minimax-m3.1-flash:AUDUSD",
        prefix_hash="adjudication_padded_hash_v1",
    )
    assert rep_aud.missed is False
    assert rep_aud.reason == "first_call"

    # Call 2: XBRUSD adjudication 26.9s later with 0 cached tokens from provider
    # Under isolated symbol context keys, this is treated as XBRUSD's FIRST_CALL, not a cache miss
    rep_xbr = detector.check(
        cached_tokens=0,
        model="minimax/minimax-m3.1-flash",
        context_key="stage2:stage2_adjudicator:minimax/minimax-m3.1-flash:XBRUSD",
        prefix_hash="adjudication_padded_hash_v1",
    )
    assert rep_xbr.missed is False
    assert rep_xbr.reason == "first_call"
    assert rep_xbr.root_cause == "FIRST_CALL"
    assert detector.get_summary()["total_misses"] == 0
