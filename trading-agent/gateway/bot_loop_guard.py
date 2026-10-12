"""
Compatibility facade shim for legacy bot_loop_guard.py.
Re-exports from canonical monika.interfaces.gateway.bot_loop_guard.
"""

from __future__ import annotations

import monika.interfaces.gateway.bot_loop_guard as _canonical

from monika.interfaces.gateway.bot_loop_guard import (
    BotLoopGuard,
    MAX_MESSAGES_WINDOW,
    MessageFingerprint,
    SIMILARITY_THRESHOLD,
    WINDOW_SECONDS,
    logger,
)

__all__ = ['BotLoopGuard', 'MAX_MESSAGES_WINDOW', 'MessageFingerprint', 'SIMILARITY_THRESHOLD', 'WINDOW_SECONDS', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
