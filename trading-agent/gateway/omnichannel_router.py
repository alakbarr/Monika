"""
Compatibility facade shim for legacy omnichannel_router.py.
Re-exports from canonical monika.interfaces.gateway.omnichannel_router.
"""

from __future__ import annotations

import monika.interfaces.gateway.omnichannel_router as _canonical

from monika.interfaces.gateway.omnichannel_router import (
    MessageEvent,
    MessageType,
    OmnichannelRouter,
    SessionSource,
    build_session_key,
    ensure_closed_code_fences,
    logger,
)

__all__ = ['MessageEvent', 'MessageType', 'OmnichannelRouter', 'SessionSource', 'build_session_key', 'ensure_closed_code_fences', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
