"""
Compatibility facade shim for legacy mcp_server.py.
Re-exports from canonical monika.interfaces.dashboard.routes.mcp_server.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.mcp_server as _canonical

from monika.interfaces.dashboard.routes.mcp_server import (
    get_dispatcher,
    list_mcp_tools,
    logger,
    mcp_post_message,
    mcp_router,
    mcp_sse_endpoint,
)

__all__ = ['get_dispatcher', 'list_mcp_tools', 'logger', 'mcp_post_message', 'mcp_router', 'mcp_sse_endpoint']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
