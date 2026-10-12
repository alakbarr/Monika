"""
Compatibility facade shim for legacy chat_tool_router.py.
Re-exports from canonical monika.interfaces.telegram.chat_tool_router.
"""

from __future__ import annotations

import monika.interfaces.telegram.chat_tool_router as _canonical

from monika.interfaces.telegram.chat_tool_router import (
    ChatToolRouter,
    logger,
)

__all__ = ['ChatToolRouter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
