"""
Compatibility facade shim for legacy websocket.py.
Re-exports from canonical monika.interfaces.dashboard.routes.websocket.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.websocket as _canonical

from monika.interfaces.dashboard.routes.websocket import (
    TokenCoalescingBuffer,
    create_ws_ticket,
    get_session_messages,
    list_sessions,
    logger,
    router,
    websocket_agent_chat,
    websocket_live_feed,
    websocket_router,
    websocket_terminal_pty,
)

__all__ = ['TokenCoalescingBuffer', 'create_ws_ticket', 'get_session_messages', 'list_sessions', 'logger', 'router', 'websocket_agent_chat', 'websocket_live_feed', 'websocket_router', 'websocket_terminal_pty']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
