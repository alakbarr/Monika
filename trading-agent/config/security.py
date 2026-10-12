"""
Compatibility facade shim for legacy security.py.
Re-exports from canonical monika.core.config.security.
"""

from __future__ import annotations

import monika.core.config.security as _canonical

from monika.core.config.security import (
    validate_env_mutation,
)

__all__ = ['validate_env_mutation']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
