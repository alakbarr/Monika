"""
Backward-compatibility facade for ClaudeRateLimiter.
Canonical location: monika.infrastructure.llm.rate_limiting.claude_rate_limiter
"""

import sys
import monika.infrastructure.llm.rate_limiting.claude_rate_limiter as _canonical

from monika.infrastructure.llm.rate_limiting.claude_rate_limiter import ClaudeRateLimiter

__all__ = ["ClaudeRateLimiter"]

sys.modules[__name__] = _canonical
