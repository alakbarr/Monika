"""
Compatibility facade shim for legacy discord_notifier.py.
Re-exports from canonical monika.infrastructure.infra.discord_notifier.
"""

from __future__ import annotations

import monika.infrastructure.infra.discord_notifier as _canonical

from monika.infrastructure.infra.discord_notifier import (
    DiscordNotifier,
)

__all__ = ['DiscordNotifier']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
