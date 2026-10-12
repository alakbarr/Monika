"""
Compatibility facade shim for legacy openrouter_rate_limiter.py.
Re-exports from canonical monika.infrastructure.api.openrouter_rate_limiter.
"""

from __future__ import annotations

import monika.infrastructure.api.openrouter_rate_limiter as _canonical

from monika.infrastructure.api.openrouter_rate_limiter import (
    DEFAULT_FREE_QUOTA,
    DEFAULT_FREE_QUOTA_PER_KEY,
    DEFAULT_PAID_QUOTA,
    DEFAULT_PAID_QUOTA_PER_KEY,
    OpenRouterRateLimiter,
    get_all_keys,
    get_free_keys,
    get_paid_key,
    is_free_tier_model,
)

__all__ = ['DEFAULT_FREE_QUOTA', 'DEFAULT_FREE_QUOTA_PER_KEY', 'DEFAULT_PAID_QUOTA', 'DEFAULT_PAID_QUOTA_PER_KEY', 'OpenRouterRateLimiter', 'get_all_keys', 'get_free_keys', 'get_paid_key', 'is_free_tier_model']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
