"""
Compatibility facade shim for legacy theme.py.
Re-exports from canonical monika.interfaces.cli.chat.theme.
"""

from __future__ import annotations

import monika.interfaces.cli.chat.theme as _canonical

from monika.interfaces.cli.chat.theme import (
    BOX_DOUBLE_BOTTOM_LEFT,
    BOX_DOUBLE_BOTTOM_RIGHT,
    BOX_DOUBLE_HORIZONTAL,
    BOX_DOUBLE_TOP_LEFT,
    BOX_DOUBLE_TOP_RIGHT,
    BOX_DOUBLE_VERTICAL,
    BOX_HORIZONTAL,
    BOX_ROUND_BOTTOM_LEFT,
    BOX_ROUND_BOTTOM_RIGHT,
    BOX_ROUND_TOP_LEFT,
    BOX_ROUND_TOP_RIGHT,
    BOX_VERTICAL,
    ChatPalette,
    GLYPH_AGENT,
    GLYPH_ARROW_RIGHT,
    GLYPH_BRANCH,
    GLYPH_CORNER,
    GLYPH_DOT,
    GLYPH_ERROR,
    GLYPH_SUCCESS,
    GLYPH_THINK,
    GLYPH_TOOL,
    GLYPH_USER,
    GLYPH_VERTICAL,
    GLYPH_WARN,
    get_chat_palette,
)

__all__ = ['BOX_DOUBLE_BOTTOM_LEFT', 'BOX_DOUBLE_BOTTOM_RIGHT', 'BOX_DOUBLE_HORIZONTAL', 'BOX_DOUBLE_TOP_LEFT', 'BOX_DOUBLE_TOP_RIGHT', 'BOX_DOUBLE_VERTICAL', 'BOX_HORIZONTAL', 'BOX_ROUND_BOTTOM_LEFT', 'BOX_ROUND_BOTTOM_RIGHT', 'BOX_ROUND_TOP_LEFT', 'BOX_ROUND_TOP_RIGHT', 'BOX_VERTICAL', 'ChatPalette', 'GLYPH_AGENT', 'GLYPH_ARROW_RIGHT', 'GLYPH_BRANCH', 'GLYPH_CORNER', 'GLYPH_DOT', 'GLYPH_ERROR', 'GLYPH_SUCCESS', 'GLYPH_THINK', 'GLYPH_TOOL', 'GLYPH_USER', 'GLYPH_VERTICAL', 'GLYPH_WARN', 'get_chat_palette']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
