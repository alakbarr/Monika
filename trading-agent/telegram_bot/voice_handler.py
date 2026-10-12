"""
Compatibility facade shim for legacy voice_handler.py.
Re-exports from canonical monika.interfaces.telegram.voice_handler.
"""

from __future__ import annotations

import monika.interfaces.telegram.voice_handler as _canonical

from monika.interfaces.telegram.voice_handler import (
    VoiceHandler,
    logger,
)

__all__ = ['VoiceHandler', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
