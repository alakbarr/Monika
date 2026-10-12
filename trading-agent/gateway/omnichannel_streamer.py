"""
Compatibility facade shim for legacy omnichannel_streamer.py.
Re-exports from canonical monika.interfaces.gateway.omnichannel_streamer.
"""

from __future__ import annotations

import monika.interfaces.gateway.omnichannel_streamer as _canonical

from monika.interfaces.gateway.omnichannel_streamer import (
    OmnichannelStreamer,
    balance_code_fences,
    logger,
    scrub_thinking_tokens,
)

__all__ = ['OmnichannelStreamer', 'balance_code_fences', 'logger', 'scrub_thinking_tokens']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
