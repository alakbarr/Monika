"""
Compatibility facade shim for legacy pty_bridge.py.
Re-exports from canonical monika.interfaces.dashboard.pty_bridge.
"""

from __future__ import annotations

import monika.interfaces.dashboard.pty_bridge as _canonical

from monika.interfaces.dashboard.pty_bridge import (
    PtyBridgeManager,
    PtySession,
    get_pty_bridge_manager,
    logger,
)

__all__ = ['PtyBridgeManager', 'PtySession', 'get_pty_bridge_manager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
