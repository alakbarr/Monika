# ==============================================================================
# File: cli/chat/theme.py
# Description: Design System tokens, Glyphs, and Palette for Monika CLI Chat
# ==============================================================================

"""
Design tokens, typographic glyphs, and box-drawing elements for Monika Chat CLI.
Harmonized with Monika's institutional brass & phosphor amber aesthetic.
"""

from dataclasses import dataclass
from typing import Dict, Any
from cli.theme import (
    PHOSPHOR_AMBER,
    BRASS,
    BULL_PROFIT,
    BEAR_LOSS,
    MUTED,
    DIM,
    PAPER,
    CHARCOAL,
    SURFACE,
    BORDER,
    get_theme,
    ThemePack,
)

# Semantic UI Glyphs
GLYPH_USER = "❯"
GLYPH_AGENT = "◈"
GLYPH_THINK = "💭"
GLYPH_TOOL = "⚙"
GLYPH_SUCCESS = "✔"
GLYPH_ERROR = "✖"
GLYPH_WARN = "⚠"
GLYPH_ARROW_RIGHT = "→"
GLYPH_DOT = "•"
GLYPH_BRANCH = "├──"
GLYPH_CORNER = "└──"
GLYPH_VERTICAL = "│"

# Box Elements
BOX_ROUND_TOP_LEFT = "╭"
BOX_ROUND_TOP_RIGHT = "╮"
BOX_ROUND_BOTTOM_LEFT = "╰"
BOX_ROUND_BOTTOM_RIGHT = "╯"
BOX_HORIZONTAL = "─"
BOX_VERTICAL = "│"
BOX_DOUBLE_HORIZONTAL = "═"
BOX_DOUBLE_VERTICAL = "║"
BOX_DOUBLE_TOP_LEFT = "╔"
BOX_DOUBLE_TOP_RIGHT = "╗"
BOX_DOUBLE_BOTTOM_LEFT = "╚"
BOX_DOUBLE_BOTTOM_RIGHT = "╝"


@dataclass
class ChatPalette:
    """Color tokens tailored for interactive CLI chat."""
    primary: str = PHOSPHOR_AMBER
    accent: str = BRASS
    user: str = BRASS
    agent: str = PHOSPHOR_AMBER
    thinking: str = MUTED
    thinking_border: str = DIM
    tool: str = BRASS
    tool_dim: str = MUTED
    success: str = BULL_PROFIT
    danger: str = BEAR_LOSS
    warning: str = BRASS
    text: str = PAPER
    muted: str = MUTED
    dim: str = DIM
    border: str = BORDER
    surface: str = SURFACE
    background: str = CHARCOAL


def get_chat_palette(theme_name: str = "retro_vintage") -> ChatPalette:
    """Derive chat color tokens from active system ThemePack."""
    tp: ThemePack = get_theme(theme_name)
    return ChatPalette(
        primary=tp.primary,
        accent=tp.accent,
        user=tp.accent,
        agent=tp.primary,
        thinking=tp.muted,
        thinking_border=tp.dim,
        tool=tp.accent,
        tool_dim=tp.muted,
        success=tp.profit,
        danger=tp.loss,
        warning=tp.accent,
        text=tp.text,
        muted=tp.muted,
        dim=tp.dim,
        border=tp.border,
        surface=tp.surface,
        background=tp.background,
    )
