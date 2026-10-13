"""
Backward-compatibility facade for GroqRateLimiter.
Canonical location: monika.infrastructure.llm.rate_limiting.groq_rate_limiter
"""

import sys
import monika.infrastructure.llm.rate_limiting.groq_rate_limiter as _canonical

from monika.infrastructure.llm.rate_limiting.groq_rate_limiter import (
    DEFAULT_QUOTA,
    GROQ_QUOTA,
    _STATE_FILE,
    GroqRateLimiter,
    _num_keys,
    get_api_keys,
)

__all__ = [
    "GroqRateLimiter",
    "get_api_keys",
    "GROQ_QUOTA",
    "DEFAULT_QUOTA",
    "_num_keys",
    "_STATE_FILE",
]

sys.modules[__name__] = _canonical
