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
