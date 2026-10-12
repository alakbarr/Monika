"""
Compatibility facade shim for legacy trading_commands.py.
Re-exports from canonical monika.interfaces.telegram.handlers.trading_commands.
"""

from __future__ import annotations

import monika.interfaces.telegram.handlers.trading_commands as _canonical

from monika.interfaces.telegram.handlers.trading_commands import (
    CommandDescriptor,
    execute_trading_command,
)

__all__ = ['CommandDescriptor', 'execute_trading_command']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
