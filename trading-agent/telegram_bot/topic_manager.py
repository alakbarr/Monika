"""
Compatibility facade shim for legacy topic_manager.py.
Re-exports from canonical monika.interfaces.telegram.topic_manager.
"""

from __future__ import annotations

import monika.interfaces.telegram.topic_manager as _canonical

from monika.interfaces.telegram.topic_manager import (
    TopicManager,
    logger,
)

__all__ = ['TopicManager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
