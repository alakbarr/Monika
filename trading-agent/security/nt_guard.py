"""
Compatibility facade shim for legacy nt_guard.py.
Re-exports from canonical monika.core.security.nt_guard.
"""

from __future__ import annotations

import monika.core.security.nt_guard as _canonical

from monika.core.security.nt_guard import (
    SecurityViolationError,
    assert_safe_nt_path,
    is_dangerous_nt_namespace,
    sanitize_path,
)

__all__ = ['SecurityViolationError', 'assert_safe_nt_path', 'is_dangerous_nt_namespace', 'sanitize_path']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
