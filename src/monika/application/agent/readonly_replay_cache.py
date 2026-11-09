# ==============================================================================
# File: agent/readonly_replay_cache.py
# Monika Cognitive Deliberation: Read-Only Tool Replay & Deterministic Cache
# ==============================================================================

"""
Read-Only Tool Replay & Deterministic Cache.

Prevents redundant execution and token waste across multi-round debates,
subagent investigations, and trajectory replay evaluations:
- Caches results of idempotent read-only tools:
  - get_historical_rates / get_ohlcv
  - get_economic_calendar
  - get_macro_indicator
  - get_instrument_specs
  - calculate_factor / calculate_indicators
- Configurable TTL (time-to-live) per tool category.
- Thread-safe in-memory cache with eviction and replay preservation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from monika.core.primitives.bounded_lru_cache import BoundedLRUCache

logger = logging.getLogger("TradingAgent.Agent.ReadOnlyReplayCache")


@dataclass
class CacheEntry:
    result: Any
    created_at: float
    ttl_seconds: float

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.ttl_seconds)


class ReadOnlyReplayCache:
    """Thread-safe bounded TTL replay cache for read-only agent tools."""

    _instance: Optional[ReadOnlyReplayCache] = None
    _lock = threading.Lock()

    def __init__(self, default_ttl_seconds: float = 300.0, maxsize: int = 1000):
        self.default_ttl = default_ttl_seconds
        self.maxsize = maxsize
        self._bounded_cache: BoundedLRUCache[str, Any] = BoundedLRUCache(
            maxsize=maxsize, default_ttl_seconds=default_ttl_seconds
        )

    @classmethod
    def get_instance(cls) -> ReadOnlyReplayCache:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                try:
                    from monika.core.primitives.compaction import get_compaction_registry

                    get_compaction_registry().register(cls._instance)
                except Exception:
                    pass
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (useful for test isolation)."""
        with cls._lock:
            if cls._instance is not None:
                try:
                    from monika.core.primitives.compaction import get_compaction_registry

                    get_compaction_registry().unregister(cls._instance)
                except Exception:
                    pass
                cls._instance.clear()
            cls._instance = None

    @staticmethod
    def _make_key(tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Generates deterministic SHA-256 hash key with tool prefix."""
        t_norm = tool_name.lower().strip()
        try:
            serialized_args = json.dumps(kwargs, sort_keys=True, default=str)
        except Exception:
            serialized_args = str(sorted(kwargs.items()))
        raw = f"{t_norm}:{serialized_args}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{t_norm}:{h}"

    def get(self, tool_name: str, kwargs: Dict[str, Any]) -> Optional[Any]:
        """Retrieves cached result if present and unexpired."""
        key = self._make_key(tool_name, kwargs)
        res = self._bounded_cache.get(key)
        if res is not None:
            logger.debug(f"[ReplayCache] HIT for tool '{tool_name}' (key: {key[:12]})")
        return res

    def put(
        self,
        tool_name: str,
        kwargs: Dict[str, Any],
        result: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Stores tool execution result with TTL."""
        key = self._make_key(tool_name, kwargs)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        self._bounded_cache.put(key, result, ttl_seconds=ttl)

    def reap_expired(self) -> int:
        """Active reaper: purges all expired entries to prevent 24/7 memory accumulation."""
        return self._bounded_cache.reap_expired()

    def invalidate(self, tool_name: Optional[str] = None) -> int:
        """Invalidates all cached entries, or all entries for a specific tool."""
        if tool_name is None:
            return self._bounded_cache.clear()
        prefix = f"{tool_name.lower().strip()}:"
        return self._bounded_cache.invalidate_prefix(prefix)

    def clear(self) -> int:
        """Alias for invalidate() to clear entire cache."""
        return self.invalidate()

    def compact(self, tier: int = 1) -> int:
        """
        Implements CompactionTarget protocol for Progressive Memory Compaction (Pillar 5):
        - Tier 1: Soft prune (reap expired TTL entries).
        - Tier 2: Medium prune (reap expired, and clear cache if exceeding half capacity).
        - Tier 3: Aggressive prune (emergency full clear).
        """
        if tier >= 3:
            return self.clear()
        reaped = self.reap_expired()
        if tier >= 2 and len(self._bounded_cache) > (self.maxsize // 2):
            reaped += self.clear()
        return reaped

    @property
    def stats(self) -> Dict[str, Any]:
        """Returns cache telemetry."""
        return self._bounded_cache.stats
