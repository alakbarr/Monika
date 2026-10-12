"""
Compatibility facade shim for legacy chat_compaction.py.
Re-exports from canonical monika.interfaces.telegram.chat_compaction.
"""

from __future__ import annotations

import monika.interfaces.telegram.chat_compaction as _canonical

from monika.interfaces.telegram.chat_compaction import (
    ChatMicroCompactor,
    logger,
)

__all__ = ['ChatMicroCompactor', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
