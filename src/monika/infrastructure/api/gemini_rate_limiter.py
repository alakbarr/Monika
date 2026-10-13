"""
Backward-compatibility facade for GeminiRateLimiter.
Canonical location: monika.infrastructure.llm.rate_limiting.gemini_rate_limiter
"""

import sys
import monika.infrastructure.llm.rate_limiting.gemini_rate_limiter as _canonical

from monika.infrastructure.llm.rate_limiting.gemini_rate_limiter import (
    GeminiRateLimiter,
    configure_from_settings,
    get_quota_for_model,
)

__all__ = [
    "GeminiRateLimiter",
    "configure_from_settings",
    "get_quota_for_model",
]

sys.modules[__name__] = _canonical
