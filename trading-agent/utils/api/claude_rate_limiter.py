"""
Compatibility facade shim for legacy claude_rate_limiter.py.
Re-exports from canonical monika.infrastructure.api.claude_rate_limiter.
"""

from __future__ import annotations

import monika.infrastructure.api.claude_rate_limiter as _canonical

from monika.infrastructure.api.claude_rate_limiter import (
    ClaudeRateLimiter,
)

__all__ = ['ClaudeRateLimiter']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
