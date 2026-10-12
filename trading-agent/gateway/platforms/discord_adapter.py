"""
Compatibility facade shim for legacy discord_adapter.py.
Re-exports from canonical monika.interfaces.gateway.platforms.discord_adapter.
"""

from __future__ import annotations

import monika.interfaces.gateway.platforms.discord_adapter as _canonical

from monika.interfaces.gateway.platforms.discord_adapter import (
    DiscordPlatformAdapter,
    logger,
)

__all__ = ['DiscordPlatformAdapter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
