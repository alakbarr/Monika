"""
Compatibility facade shim for legacy prompt.py.
Re-exports from canonical monika.interfaces.cli.chat.prompt.
"""

from __future__ import annotations

import monika.interfaces.cli.chat.prompt as _canonical

from monika.interfaces.cli.chat.prompt import (
    ChatPromptManager,
)

__all__ = ['ChatPromptManager']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
