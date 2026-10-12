"""
Compatibility facade shim for legacy rbac.py.
Re-exports from canonical monika.interfaces.dashboard.rbac.
"""

from __future__ import annotations

import monika.interfaces.dashboard.rbac as _canonical

from monika.interfaces.dashboard.rbac import (
    Role,
    logger,
    require_role,
    resolve_role,
)

__all__ = ['Role', 'logger', 'require_role', 'resolve_role']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
