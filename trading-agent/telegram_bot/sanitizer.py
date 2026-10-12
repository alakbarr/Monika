"""
Compatibility facade shim for legacy sanitizer.py.
Re-exports from canonical monika.interfaces.telegram.sanitizer.
"""

from __future__ import annotations

import monika.interfaces.telegram.sanitizer as _canonical

from monika.interfaces.telegram.sanitizer import (
    ASCII_EMOTICON_PATTERN,
    EMOJI_PATTERN,
    sanitize_telegram_html,
    strip_emojis_and_emoticons,
)

__all__ = ['ASCII_EMOTICON_PATTERN', 'EMOJI_PATTERN', 'sanitize_telegram_html', 'strip_emojis_and_emoticons']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
