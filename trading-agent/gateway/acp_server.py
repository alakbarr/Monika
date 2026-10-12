"""
Compatibility facade shim for legacy acp_server.py.
Re-exports from canonical monika.interfaces.gateway.acp_server.
"""

from __future__ import annotations

import monika.interfaces.gateway.acp_server as _canonical

from monika.interfaces.gateway.acp_server import (
    AcpServer,
    logger,
)

__all__ = ['AcpServer', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
