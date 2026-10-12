"""
Compatibility facade shim for legacy indicator_sanitizer.py.
Re-exports from canonical monika.core.validation.indicator_sanitizer.
"""

from __future__ import annotations

import monika.core.validation.indicator_sanitizer as _canonical

from monika.core.validation.indicator_sanitizer import (
    safe_float,
)

__all__ = ['safe_float']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
