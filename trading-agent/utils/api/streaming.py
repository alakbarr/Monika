"""
Compatibility facade shim for legacy streaming.py.
Re-exports from canonical monika.infrastructure.api.streaming.
"""

from __future__ import annotations

import monika.infrastructure.api.streaming as _canonical

from monika.infrastructure.api.streaming import (
    StreamConfig,
    StreamResult,
    StreamSafetyTimeoutError,
    StreamTimeoutError,
    StreamWriterFence,
    StreamingHeartbeatMonitor,
    consume_sse_stream,
    streaming_request,
)

__all__ = ['StreamConfig', 'StreamResult', 'StreamSafetyTimeoutError', 'StreamTimeoutError', 'StreamWriterFence', 'StreamingHeartbeatMonitor', 'consume_sse_stream', 'streaming_request']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
