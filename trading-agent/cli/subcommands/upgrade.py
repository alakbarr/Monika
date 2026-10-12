"""
Compatibility facade shim for legacy upgrade.py.
Re-exports from canonical monika.interfaces.cli.subcommands.upgrade.
"""

from __future__ import annotations

import monika.interfaces.cli.subcommands.upgrade as _canonical

from monika.interfaces.cli.subcommands.upgrade import (
    UpgradeSubcommand,
)

__all__ = ['UpgradeSubcommand']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
