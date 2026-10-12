"""
Compatibility facade shim for legacy chat_agent.py.
Re-exports from canonical monika.interfaces.telegram.chat_agent.
"""

from __future__ import annotations

import monika.interfaces.telegram.chat_agent as _canonical

from monika.interfaces.telegram.chat_agent import (
    ChatAgent,
    HISTORY_WINDOW,
    MAX_HISTORY_CHARS,
    PendingAction,
    SESSION_TIMEOUT_HOURS,
    TELEGRAM_MAX_CHARS,
    TelegramChatAgent,
    _sanitize_telegram_format,
    get_client_for_task,
    get_session,
)

__all__ = ['ChatAgent', 'HISTORY_WINDOW', 'MAX_HISTORY_CHARS', 'PendingAction', 'SESSION_TIMEOUT_HOURS', 'TELEGRAM_MAX_CHARS', 'TelegramChatAgent', '_sanitize_telegram_format', 'get_client_for_task', 'get_session']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
