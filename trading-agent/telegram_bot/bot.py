"""
Compatibility facade shim for legacy bot.py.
Re-exports from canonical monika.interfaces.telegram.bot.
"""

from __future__ import annotations

import monika.interfaces.telegram.bot as _canonical

from monika.interfaces.telegram.bot import (
    IgnoreNetworkErrorFilter,
    TelegramBot,
    TelegramController,
    logger,
)

__all__ = ['IgnoreNetworkErrorFilter', 'TelegramBot', 'TelegramController', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
