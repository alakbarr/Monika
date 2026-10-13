"""
Backward-compatibility facade for streaming.
Canonical location: monika.infrastructure.llm.rate_limiting.streaming
"""

import sys
import monika.infrastructure.llm.rate_limiting.streaming as _canonical

from monika.infrastructure.llm.rate_limiting.streaming import (
    StreamConfig,
    StreamingHeartbeatMonitor,
    StreamResult,
    StreamSafetyTimeoutError,
    StreamTimeoutError,
    StreamWriterFence,
    consume_sse_stream,
    streaming_request,
)

__all__ = [
    "StreamTimeoutError",
    "StreamSafetyTimeoutError",
    "StreamConfig",
    "StreamResult",
    "StreamWriterFence",
    "StreamingHeartbeatMonitor",
    "consume_sse_stream",
    "streaming_request",
]

sys.modules[__name__] = _canonical
