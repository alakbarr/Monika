"""
Compatibility facade shim for legacy mcp.py.
Re-exports from canonical monika.interfaces.cli.subcommands.mcp.
"""

from __future__ import annotations

import monika.interfaces.cli.subcommands.mcp as _canonical

from monika.interfaces.cli.subcommands.mcp import (
    McpSubcommand,
)

__all__ = ['McpSubcommand']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
