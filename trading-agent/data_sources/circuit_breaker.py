"""
File: data_sources/circuit_breaker.py
Data Feed Circuit Breaker & Freshness Sentinel.
Monitors freshness across MT5 ticks, FRED macro series, Finnhub news,
and Economic Calendar. Automatically trips execution gates and alerts
EventBus when critical feeds become stale or fail.
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger("TradingAgent.DataSources.CircuitBreaker")


@dataclass
class FeedStatus:
    name: str
    last_heartbeat: Optional[float] = None
    ttl_seconds: float = 300.0
    is_critical: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    tripped: bool = False
    trip_reason: Optional[str] = None
    trip_timestamp: Optional[float] = None
    cooldown_seconds: float = 300.0

    @property
    def age_seconds(self) -> float:
        if self.last_heartbeat is None:
            return float("inf")
        return max(0.0, time.time() - self.last_heartbeat)

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > self.ttl_seconds


class DataFeedCircuitBreaker:
    """
    Central circuit breaker for all incoming data feeds (MT5, FRED, Finnhub, Calendar, Sentiment).
    Prevents execution on stale/hallucinated macro data by tripping safety gates.
    """

    DEFAULT_TTLS: Dict[str, float] = {
        "mt5_ticks": 120.0,          # 2 minutes: tick feed frozen
        "fred": 345600.0,            # 96 hours: daily series / weekends / holiday buffers
        "finnhub": 3600.0,           # 1 hour: news feed
        "economic_calendar": 21600.0,# 6 hours: calendar releases
        "sentiment": 7200.0,         # 2 hours: crowd sentiment
        "market_quotes": 300.0,      # 5 minutes: price quotes
    }

    def __init__(self, custom_ttls: Optional[Dict[str, float]] = None):
        self.ttls = dict(self.DEFAULT_TTLS)
        if custom_ttls:
            self.ttls.update(custom_ttls)

        self._feeds: Dict[str, FeedStatus] = {}
        for name, ttl in self.ttls.items():
            self._feeds[name] = FeedStatus(name=name, ttl_seconds=ttl)

    def record_feed_heartbeat(
        self,
        feed_name: str,
        timestamp: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record fresh arrival of data for feed_name, resetting trip if previously stale."""
        key = feed_name.strip().lower()
        now_ts = timestamp if timestamp is not None else time.time()

        if key not in self._feeds:
            ttl = self.ttls.get(key, 300.0)
            self._feeds[key] = FeedStatus(name=key, ttl_seconds=ttl)

        feed = self._feeds[key]
        feed.last_heartbeat = now_ts
        if metadata:
            feed.metadata.update(metadata)

        # Auto-reset if tripped solely due to staleness and now fresh
        if feed.tripped and not feed.is_stale:
            self.reset(key, reason="Fresh data received")

    def check_feed(self, feed_name: str, now: Optional[float] = None) -> Dict[str, Any]:
        """Check status of a single feed."""
        key = feed_name.strip().lower()
        feed = self._feeds.get(key)
        if not feed:
            return {
                "name": key,
                "registered": False,
                "stale": True,
                "age_seconds": float("inf"),
                "ttl_seconds": self.ttls.get(key, 300.0),
                "tripped": False,
            }

        now_ts = now if now is not None else time.time()
        age = (now_ts - feed.last_heartbeat) if feed.last_heartbeat else float("inf")
        stale = age > feed.ttl_seconds
        return {
            "name": key,
            "registered": True,
            "stale": stale,
            "age_seconds": round(age, 2),
            "ttl_seconds": feed.ttl_seconds,
            "last_heartbeat": feed.last_heartbeat,
            "tripped": feed.tripped,
            "trip_reason": feed.trip_reason,
        }

    def is_feed_stale(self, feed_name: str, max_age_seconds: Optional[float] = None, now: Optional[float] = None) -> bool:
        """Check if feed_name is older than its TTL or max_age_seconds."""
        key = feed_name.strip().lower()
        feed = self._feeds.get(key)
        if not feed or feed.last_heartbeat is None:
            return True
        now_ts = now if now is not None else time.time()
        threshold = max_age_seconds if max_age_seconds is not None else feed.ttl_seconds
        return (now_ts - feed.last_heartbeat) > threshold

    def trip(self, feed_name: str, reason: str, cooldown_seconds: float = 300.0) -> bool:
        """Trip circuit breaker for feed_name and emit CircuitBreakerEvent."""
        key = feed_name.strip().lower()
        if key not in self._feeds:
            self._feeds[key] = FeedStatus(name=key, ttl_seconds=self.ttls.get(key, 300.0))

        feed = self._feeds[key]
        feed.tripped = True
        feed.trip_reason = reason
        feed.trip_timestamp = time.time()
        feed.cooldown_seconds = cooldown_seconds

        logger.critical(f"[DataFeedCircuitBreaker] TRIPPED on '{key}': {reason}")

        # Publish CircuitBreakerEvent to EventBus if available
        self._publish_event(component=f"DataFeed:{key}", reason=reason, is_active=True, cooldown=int(cooldown_seconds))
        return True

    def reset(self, feed_name: Optional[str] = None, reason: str = "Manual reset") -> bool:
        """Reset circuit breaker for a specific feed or all feeds."""
        if feed_name is not None:
            key = feed_name.strip().lower()
            if key in self._feeds and self._feeds[key].tripped:
                self._feeds[key].tripped = False
                self._feeds[key].trip_reason = None
                self._feeds[key].trip_timestamp = None
                logger.info(f"[DataFeedCircuitBreaker] Reset feed '{key}': {reason}")
                self._publish_event(component=f"DataFeed:{key}", reason=reason, is_active=False)
                return True
            return False
        else:
            reset_any = False
            for key, feed in self._feeds.items():
                if feed.tripped:
                    feed.tripped = False
                    feed.trip_reason = None
                    feed.trip_timestamp = None
                    reset_any = True
                    self._publish_event(component=f"DataFeed:{key}", reason=reason, is_active=False)
            if reset_any:
                logger.info(f"[DataFeedCircuitBreaker] Reset all feeds: {reason}")
            return reset_any

    def is_tripped(self, feed_name: Optional[str] = None) -> bool:
        """Check if any critical feed or a specific feed is currently tripped."""
        if feed_name is not None:
            key = feed_name.strip().lower()
            return self._feeds[key].tripped if key in self._feeds else False
        return any(feed.tripped for feed in self._feeds.values())

    def get_tripped_feeds(self) -> Dict[str, Dict[str, Any]]:
        """Return all currently tripped feeds and reasons."""
        tripped = {}
        for name, feed in self._feeds.items():
            if feed.tripped:
                tripped[name] = {
                    "reason": feed.trip_reason,
                    "timestamp": feed.trip_timestamp,
                    "cooldown_seconds": feed.cooldown_seconds,
                    "age_seconds": feed.age_seconds,
                }
        return tripped

    def evaluate_all_feeds(self, auto_trip: bool = True, now: Optional[float] = None) -> Dict[str, Any]:
        """Scan all registered feeds for staleness, auto-tripping circuit breakers if enabled."""
        now_ts = now if now is not None else time.time()
        results = {}
        stale_critical = []

        for name, feed in self._feeds.items():
            age = (now_ts - feed.last_heartbeat) if feed.last_heartbeat else float("inf")
            is_stale = age > feed.ttl_seconds
            results[name] = {
                "stale": is_stale,
                "age_seconds": round(age, 2),
                "ttl_seconds": feed.ttl_seconds,
                "tripped": feed.tripped,
            }
            if is_stale and feed.is_critical:
                stale_critical.append(name)
                if auto_trip and not feed.tripped:
                    self.trip(
                        name,
                        reason=f"Feed stale: age {age:.1f}s exceeds TTL {feed.ttl_seconds:.1f}s",
                        cooldown_seconds=feed.cooldown_seconds,
                    )

        return {
            "all_healthy": len(stale_critical) == 0,
            "stale_critical": stale_critical,
            "feeds": results,
            "circuit_breaker_tripped": self.is_tripped(),
        }

    def get_health_report(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Comprehensive health report for observability dashboard & diagnostics."""
        now_ts = now if now is not None else time.time()
        report = {}
        for name, feed in self._feeds.items():
            report[name] = self.check_feed(name, now=now_ts)
        return {
            "is_tripped": self.is_tripped(),
            "tripped_feeds": self.get_tripped_feeds(),
            "feeds": report,
        }

    def _publish_event(self, component: str, reason: str, is_active: bool, cooldown: int = 0) -> None:
        """Best-effort async event emission to EventBus."""
        try:
            from utils.protocol.event_bus import get_event_bus, CircuitBreakerEvent
            bus = get_event_bus()
            event = CircuitBreakerEvent(
                component=component,
                reason=reason,
                is_active=is_active,
                cooldown_seconds=cooldown,
            )
            bus.publish_nowait(event)
        except Exception as e:
            logger.debug(f"[DataFeedCircuitBreaker] EventBus publish non-fatal error: {e}")


# Global Singleton Accessor
_GLOBAL_FEED_BREAKER: Optional[DataFeedCircuitBreaker] = None


def get_data_feed_circuit_breaker() -> DataFeedCircuitBreaker:
    """Return the global DataFeedCircuitBreaker singleton."""
    global _GLOBAL_FEED_BREAKER
    if _GLOBAL_FEED_BREAKER is None:
        _GLOBAL_FEED_BREAKER = DataFeedCircuitBreaker()
    return _GLOBAL_FEED_BREAKER


def record_feed_heartbeat(feed_name: str, timestamp: Optional[float] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Convenience helper to record feed arrival."""
    get_data_feed_circuit_breaker().record_feed_heartbeat(feed_name, timestamp, metadata)
