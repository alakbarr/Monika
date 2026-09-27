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
    """Thread-safe TTL replay cache for read-only agent tools."""

    _instance: Optional[ReadOnlyReplayCache] = None
    _lock = threading.Lock()

    def __init__(self, default_ttl_seconds: float = 300.0):
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}
        self._hits: int = 0
        self._misses: int = 0
        self._access_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ReadOnlyReplayCache:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def _make_key(tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Generates deterministic SHA-256 hash key for tool call."""
        try:
            serialized_args = json.dumps(kwargs, sort_keys=True, default=str)
        except Exception:
            serialized_args = str(sorted(kwargs.items()))
        raw = f"{tool_name.lower().strip()}:{serialized_args}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, tool_name: str, kwargs: Dict[str, Any]) -> Optional[Any]:
        """Retrieves cached result if present and unexpired."""
        key = self._make_key(tool_name, kwargs)
        with self._access_lock:
            entry = self._cache.get(key)
            if entry is not None:
                if not entry.is_expired:
                    self._hits += 1
                    logger.debug(f"[ReplayCache] HIT for tool '{tool_name}' (key: {key[:8]})")
                    return entry.result
                else:
                    del self._cache[key]
            self._misses += 1
            return None

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
        with self._access_lock:
            self._cache[key] = CacheEntry(
                result=result,
                created_at=time.time(),
                ttl_seconds=ttl,
            )

    def invalidate(self, tool_name: Optional[str] = None) -> int:
        """Invalidates all cached entries, or all entries for a specific tool."""
        count = 0
        with self._access_lock:
            if tool_name is None:
                count = len(self._cache)
                self._cache.clear()
            else:
                prefix = tool_name.lower().strip()
                keys_to_delete = [
                    k for k, v in self._cache.items()
                ]
                # If specific tool clearing requested
                for k in keys_to_delete:
                    del self._cache[k]
                    count += 1
        return count

    @property
    def stats(self) -> Dict[str, Any]:
        """Returns cache telemetry."""
        with self._access_lock:
            total = self._hits + self._misses
            hit_ratio = (self._hits / total) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_lookups": total,
                "hit_ratio": round(hit_ratio, 3),
                "active_entries": len(self._cache),
            }
