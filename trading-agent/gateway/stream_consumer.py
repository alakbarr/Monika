"""
Compatibility facade shim for legacy stream_consumer.py.
Re-exports from canonical monika.interfaces.gateway.stream_consumer.
"""

from __future__ import annotations

import monika.interfaces.gateway.stream_consumer as _canonical

from monika.interfaces.gateway.stream_consumer import (
    LiveStreamConsumer,
    ensure_closed_code_fences,
    logger,
    scrub_thinking_tags,
)

__all__ = ['LiveStreamConsumer', 'ensure_closed_code_fences', 'logger', 'scrub_thinking_tags']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
