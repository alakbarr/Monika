"""
Compatibility facade shim for legacy renderer.py.
Re-exports from canonical monika.interfaces.cli.chat.renderer.
"""

from __future__ import annotations

import monika.interfaces.cli.chat.renderer as _canonical

from monika.interfaces.cli.chat.renderer import (
    ChatRenderer,
    ThinkingScrubber,
    get_terminal_width,
)

__all__ = ['ChatRenderer', 'ThinkingScrubber', 'get_terminal_width']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
