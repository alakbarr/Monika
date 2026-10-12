"""
Compatibility facade shim for legacy system_commands.py.
Re-exports from canonical monika.interfaces.telegram.handlers.system_commands.
"""

from __future__ import annotations

import monika.interfaces.telegram.handlers.system_commands as _canonical

from monika.interfaces.telegram.handlers.system_commands import (
    SystemCommandDescriptor,
)

__all__ = ['SystemCommandDescriptor']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
