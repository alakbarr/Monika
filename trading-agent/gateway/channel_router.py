"""
Compatibility facade shim for legacy channel_router.py.
Re-exports from canonical monika.interfaces.gateway.channel_router.
"""

from __future__ import annotations

import monika.interfaces.gateway.channel_router as _canonical

from monika.interfaces.gateway.channel_router import (
    ChannelRouter,
    logger,
)

__all__ = ['ChannelRouter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
