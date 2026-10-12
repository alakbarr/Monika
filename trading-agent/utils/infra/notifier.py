"""
Compatibility facade shim for legacy notifier.py.
Re-exports from canonical monika.infrastructure.infra.notifier.
"""

from __future__ import annotations

import monika.infrastructure.infra.notifier as _canonical

from monika.infrastructure.infra.notifier import (
    AgentNotifier,
    get_notifier,
    sanitize_telegram_html,
)

__all__ = ['AgentNotifier', 'get_notifier', 'sanitize_telegram_html']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
