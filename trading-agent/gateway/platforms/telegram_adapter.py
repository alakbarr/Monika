"""
Compatibility facade shim for legacy telegram_adapter.py.
Re-exports from canonical monika.interfaces.gateway.platforms.telegram_adapter.
"""

from __future__ import annotations

import monika.interfaces.gateway.platforms.telegram_adapter as _canonical

from monika.interfaces.gateway.platforms.telegram_adapter import (
    TelegramPlatformAdapter,
    logger,
)

__all__ = ['TelegramPlatformAdapter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
