"""
Compatibility facade shim for legacy key_validator.py.
Re-exports from canonical monika.core.config.key_validator.
"""

from __future__ import annotations

import monika.core.config.key_validator as _canonical

from monika.core.config.key_validator import (
    validate_config_key,
)

__all__ = ['validate_config_key']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
