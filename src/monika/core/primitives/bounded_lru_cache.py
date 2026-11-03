# ==============================================================================
# File: core/primitives/bounded_lru_cache.py
# Description: Thread-safe bounded LRU cache with monotonic TTL expiration.
# ==============================================================================

from __future__ import annotations

from collections import OrderedDict
import threading
import time
from typing import Any, Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BoundedLRUCache(Generic[K, V]):
    """
    Thread-safe bounded LRU cache with deterministic capacity ceiling and monotonic TTL pruning.

    Guarantees:
    - Bounded memory footprint (maxsize ceiling prevents OOM in 24/7 continuous operation).
    - Monotonic clock: time.monotonic() prevents time-warp/NTP skew issues.
    - Full support for cached None values without sentinel confusion.
    - Proactive LRU eviction of expired keys first when capacity is reached.
    """

    def __init__(self, maxsize: int = 1000, default_ttl_seconds: float = 300.0) -> None:
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize}")
        if default_ttl_seconds <= 0.0:
            raise ValueError(f"default_ttl_seconds must be > 0, got {default_ttl_seconds}")

        self.maxsize = maxsize
        self.default_ttl = default_ttl_seconds
        self._cache: OrderedDict[K, tuple[V, float, float]] = OrderedDict()  # key -> (value, created_at, ttl)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Retrieve cached value if present and unexpired."""
        now = time.monotonic()
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return default
            val, created_at, ttl = self._cache[key]
            if now > created_at + ttl:
                del self._cache[key]
                self._misses += 1
                return default
            self._cache.move_to_end(key)
            self._hits += 1
            return val

    def put(self, key: K, value: V, ttl_seconds: Optional[float] = None) -> None:
        """Store key-value pair with TTL and LRU capacity enforcement."""
        now = time.monotonic()
        ttl = ttl_seconds if (ttl_seconds is not None and ttl_seconds > 0.0) else self.default_ttl
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self.maxsize:
                # Proactively evict oldest expired entry first if one exists
                oldest_k, (_, created_at, item_ttl) = next(iter(self._cache.items()))
                if now > created_at + item_ttl:
                    del self._cache[oldest_k]
                else:
                    self._cache.popitem(last=False)
            self._cache[key] = (value, now, ttl)

    def reap_expired(self) -> int:
        """Active reaper: purges all expired entries from cache. Returns count of purged entries."""
        now = time.monotonic()
        evicted = 0
        with self._lock:
            expired_keys = [k for k, (_, c_at, ttl) in self._cache.items() if now > c_at + ttl]
            for k in expired_keys:
                del self._cache[k]
                evicted += 1
        return evicted

    def invalidate(self, key: K) -> bool:
        """Invalidate a specific key if present."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Invalidate all keys matching prefix string."""
        count = 0
        with self._lock:
            matching = [k for k in self._cache.keys() if isinstance(k, str) and k.startswith(prefix)]
            for k in matching:
                del self._cache[k]
                count += 1
        return count

    def clear(self) -> int:
        """Clear all entries and return count of cleared entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: K) -> bool:
        now = time.monotonic()
        with self._lock:
            if key not in self._cache:
                return False
            _, created_at, ttl = self._cache[key]
            if now > created_at + ttl:
                del self._cache[key]
                return False
            return True

    @property
    def stats(self) -> dict[str, Any]:
        """Return cache access telemetry."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_lookups": total,
                "hit_ratio": round(self._hits / total, 3) if total > 0 else 0.0,
                "active_entries": len(self._cache),
                "maxsize": self.maxsize,
            }
