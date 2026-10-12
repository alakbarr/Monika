"""
Compatibility facade shim for legacy groq_rate_limiter.py.
Re-exports from canonical monika.infrastructure.api.groq_rate_limiter.
"""

from __future__ import annotations

import monika.infrastructure.api.groq_rate_limiter as _canonical

from monika.infrastructure.api.groq_rate_limiter import (
    DEFAULT_QUOTA,
    DEFAULT_QUOTA_PER_KEY,
    GROQ_QUOTA,
    GROQ_QUOTA_PER_KEY,
    GroqRateLimiter,
    get_api_keys,
)

__all__ = ['DEFAULT_QUOTA', 'DEFAULT_QUOTA_PER_KEY', 'GROQ_QUOTA', 'GROQ_QUOTA_PER_KEY', 'GroqRateLimiter', 'get_api_keys']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
