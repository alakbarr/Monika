"""
Compatibility facade shim for legacy circuit_breaker.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.circuit_breaker.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.circuit_breaker as _canonical

from monika.infrastructure.data_ingestion.sources.circuit_breaker import (
    DataFeedCircuitBreaker,
    FeedStatus,
    _GLOBAL_FEED_BREAKER,
    get_data_feed_circuit_breaker,
    logger,
    record_feed_heartbeat,
)

__all__ = ['DataFeedCircuitBreaker', 'FeedStatus', '_GLOBAL_FEED_BREAKER', 'get_data_feed_circuit_breaker', 'logger', 'record_feed_heartbeat']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
