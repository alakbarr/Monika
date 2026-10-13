"""
Backward-compatibility facade for OpenRouterRateLimiter.
Canonical location: monika.infrastructure.llm.rate_limiting.openrouter_rate_limiter
"""

import sys
import monika.infrastructure.llm.rate_limiting.openrouter_rate_limiter as _canonical

from monika.infrastructure.llm.rate_limiting.openrouter_rate_limiter import (
    _STATE_FILE,
    OpenRouterRateLimiter,
    get_all_keys,
    get_free_keys,
    get_paid_key,
    is_free_tier_model,
)

__all__ = [
    "OpenRouterRateLimiter",
    "get_paid_key",
    "get_free_keys",
    "get_all_keys",
    "is_free_tier_model",
    "_STATE_FILE",
]

sys.modules[__name__] = _canonical
