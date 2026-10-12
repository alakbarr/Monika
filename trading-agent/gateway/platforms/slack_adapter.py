"""
Compatibility facade shim for legacy slack_adapter.py.
Re-exports from canonical monika.interfaces.gateway.platforms.slack_adapter.
"""

from __future__ import annotations

import monika.interfaces.gateway.platforms.slack_adapter as _canonical

from monika.interfaces.gateway.platforms.slack_adapter import (
    SlackPlatformAdapter,
    logger,
)

__all__ = ['SlackPlatformAdapter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
