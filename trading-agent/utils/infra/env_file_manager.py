"""
Compatibility facade shim for legacy env_file_manager.py.
Re-exports from canonical monika.infrastructure.infra.env_file_manager.
"""

from __future__ import annotations

import monika.infrastructure.infra.env_file_manager as _canonical

from monika.infrastructure.infra.env_file_manager import (
    EnvFileManager,
)

__all__ = ['EnvFileManager']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
