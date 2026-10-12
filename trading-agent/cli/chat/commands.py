"""
Compatibility facade shim for legacy commands.py.
Re-exports from canonical monika.interfaces.cli.chat.commands.
"""

from __future__ import annotations

import monika.interfaces.cli.chat.commands as _canonical

from monika.interfaces.cli.chat.commands import (
    AVAILABLE_THEMES,
    ChatCommandRouter,
    CommandResult,
    logger,
)

__all__ = ['AVAILABLE_THEMES', 'ChatCommandRouter', 'CommandResult', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
