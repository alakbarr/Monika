"""
Compatibility facade shim for legacy completer.py.
Re-exports from canonical monika.interfaces.cli.chat.completer.
"""

from __future__ import annotations

import monika.interfaces.cli.chat.completer as _canonical

from monika.interfaces.cli.chat.completer import (
    ChatCommandCompleter,
)

__all__ = ['ChatCommandCompleter']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
