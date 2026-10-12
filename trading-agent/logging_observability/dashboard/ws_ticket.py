"""
Compatibility facade shim for legacy ws_ticket.py.
Re-exports from canonical monika.interfaces.dashboard.ws_ticket.
"""

from __future__ import annotations

import monika.interfaces.dashboard.ws_ticket as _canonical

from monika.interfaces.dashboard.ws_ticket import (
    DEFAULT_TICKET_TTL_SECONDS,
    TicketPayload,
    WsTicketManager,
    get_ws_ticket_manager,
    logger,
)

__all__ = ['DEFAULT_TICKET_TTL_SECONDS', 'TicketPayload', 'WsTicketManager', 'get_ws_ticket_manager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
