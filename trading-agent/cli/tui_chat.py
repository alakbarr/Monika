"""
Compatibility facade shim for legacy tui_chat.py.
Re-exports from canonical monika.interfaces.cli.tui_chat.
"""

from __future__ import annotations

import monika.interfaces.cli.tui_chat as _canonical

from monika.interfaces.cli.tui_chat import (
    CHAT_SCREEN_CSS,
    ChatScreen,
    DEFAULT_API_URL,
    is_ws_alive,
    logger,
    run_cli_chat,
)

__all__ = ['CHAT_SCREEN_CSS', 'ChatScreen', 'DEFAULT_API_URL', 'is_ws_alive', 'logger', 'run_cli_chat']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
