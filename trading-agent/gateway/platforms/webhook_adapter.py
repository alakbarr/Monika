"""
Compatibility facade shim for legacy webhook_adapter.py.
Re-exports from canonical monika.interfaces.gateway.platforms.webhook_adapter.
"""

from __future__ import annotations

import monika.interfaces.gateway.platforms.webhook_adapter as _canonical

from monika.interfaces.gateway.platforms.webhook_adapter import (
    WebhookPlatformAdapter,
    logger,
)

__all__ = ['WebhookPlatformAdapter', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
