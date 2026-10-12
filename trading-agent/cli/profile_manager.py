"""
Compatibility facade shim for legacy profile_manager.py.
Re-exports from canonical monika.interfaces.cli.profile_manager.
"""

from __future__ import annotations

import monika.interfaces.cli.profile_manager as _canonical

from monika.interfaces.cli.profile_manager import (
    ProfileInfo,
    ProfileManager,
    logger,
)

__all__ = ['ProfileInfo', 'ProfileManager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
