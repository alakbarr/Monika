"""
Compatibility facade shim for legacy db_backup.py.
Re-exports from canonical monika.infrastructure.infra.db_backup.
"""

from __future__ import annotations

import monika.infrastructure.infra.db_backup as _canonical

from monika.infrastructure.infra.db_backup import (
    create_backup,
)

__all__ = ['create_backup']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
