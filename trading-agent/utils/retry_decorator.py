"""
Compatibility facade shim for legacy retry_decorator.py.
Re-exports from canonical monika.core.primitives.retry.
"""

from __future__ import annotations

import monika.core.primitives.retry as _canonical

from monika.core.primitives.retry import (
    F,
    logger,
    retryable,
)

__all__ = ['F', 'logger', 'retryable']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
