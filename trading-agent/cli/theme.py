"""
Compatibility facade shim for legacy theme.py.
Re-exports from canonical monika.interfaces.cli.theme.
"""

from __future__ import annotations

import monika.interfaces.cli.theme as _canonical

from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BORDER,
    BRASS,
    BULL_PROFIT,
    CHARCOAL,
    DIM,
    LEDGER_BOX,
    MONIKA_THEME,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
    SURFACE,
    ThemePack,
    build_chat_css,
    build_tui_css,
    get_console,
    get_theme,
    persist_theme_to_settings,
    stamp_err,
    stamp_exec,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

__all__ = ['BEAR_LOSS', 'BORDER', 'BRASS', 'BULL_PROFIT', 'CHARCOAL', 'DIM', 'LEDGER_BOX', 'MONIKA_THEME', 'MUTED', 'PAPER', 'PHOSPHOR_AMBER', 'SURFACE', 'ThemePack', 'build_chat_css', 'build_tui_css', 'get_console', 'get_theme', 'persist_theme_to_settings', 'stamp_err', 'stamp_exec', 'stamp_info', 'stamp_ok', 'stamp_warn']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
