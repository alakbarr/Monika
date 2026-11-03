# ==============================================================================
# File: tests/core/test_bounded_lru_cache.py
# Description: Unit and concurrency tests for BoundedLRUCache & ReadOnlyReplayCache.
# ==============================================================================

import threading
import time
from typing import Any

import pytest

from monika.application.agent.readonly_replay_cache import ReadOnlyReplayCache
from monika.core.primitives.bounded_lru_cache import BoundedLRUCache


def test_bounded_lru_cache_basic_put_get():
    cache: BoundedLRUCache[str, int] = BoundedLRUCache(maxsize=3, default_ttl_seconds=10.0)
    assert len(cache) == 0

    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") is None
    assert "a" in cache
    assert "c" not in cache


def test_bounded_lru_cache_capacity_eviction():
    cache: BoundedLRUCache[str, int] = BoundedLRUCache(maxsize=3, default_ttl_seconds=10.0)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert len(cache) == 3

    # Access "a" so "b" becomes the least recently used
    assert cache.get("a") == 1

    # Insert "d", which should evict "b"
    cache.put("d", 4)
    assert len(cache) == 3
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_bounded_lru_cache_ttl_expiration():
    cache: BoundedLRUCache[str, str] = BoundedLRUCache(maxsize=5, default_ttl_seconds=0.1)
    cache.put("temp", "val")
    assert cache.get("temp") == "val"
    assert "temp" in cache

    time.sleep(0.12)
    assert cache.get("temp") is None
    assert "temp" not in cache


def test_bounded_lru_cache_reap_expired():
    cache: BoundedLRUCache[str, str] = BoundedLRUCache(maxsize=10, default_ttl_seconds=0.1)
    cache.put("k1", "v1", ttl_seconds=0.05)
    cache.put("k2", "v2", ttl_seconds=0.05)
    cache.put("k3", "v3", ttl_seconds=10.0)

    time.sleep(0.07)
    evicted = cache.reap_expired()
    assert evicted == 2
    assert len(cache) == 1
    assert cache.get("k3") == "v3"


def test_bounded_lru_cache_none_values():
    cache: BoundedLRUCache[str, Any] = BoundedLRUCache(maxsize=5, default_ttl_seconds=10.0)
    cache.put("empty", None)
    assert "empty" in cache
    assert cache.get("empty", default="sentinel") is None
    assert cache.get("nonexistent", default="sentinel") == "sentinel"


def test_bounded_lru_cache_invalidation():
    cache: BoundedLRUCache[str, int] = BoundedLRUCache(maxsize=10, default_ttl_seconds=10.0)
    cache.put("tool:rates:1", 100)
    cache.put("tool:rates:2", 200)
    cache.put("tool:other:1", 300)

    assert cache.invalidate_prefix("tool:rates:") == 2
    assert len(cache) == 1
    assert cache.get("tool:other:1") == 300

    cache.clear()
    assert len(cache) == 0


def test_bounded_lru_cache_thread_concurrency():
    cache: BoundedLRUCache[str, int] = BoundedLRUCache(maxsize=50, default_ttl_seconds=5.0)
    num_threads = 8
    ops_per_thread = 200

    def worker(tid: int):
        for i in range(ops_per_thread):
            key = f"key_{tid}_{i % 20}"
            cache.put(key, i)
            _ = cache.get(key)
            if i % 10 == 0:
                cache.reap_expired()

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cache) <= 50
    stats = cache.stats
    assert stats["active_entries"] <= 50
    assert stats["total_lookups"] > 0


def test_readonly_replay_cache_bounded():
    ReadOnlyReplayCache.reset()
    try:
        rc = ReadOnlyReplayCache(default_ttl_seconds=10.0, maxsize=5)
        for i in range(10):
            rc.put("get_price", {"symbol": f"SYM_{i}"}, f"result_{i}")

        stats = rc.stats
        assert stats["active_entries"] <= 5
        assert stats["maxsize"] == 5

        # Check replay retrieval
        res = rc.get("get_price", {"symbol": "SYM_9"})
        assert res == "result_9"
    finally:
        ReadOnlyReplayCache.reset()
