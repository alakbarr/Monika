"""
Backward-compatibility facade for http_retry.
Canonical location: monika.infrastructure.llm.rate_limiting.http_retry
"""

from monika.infrastructure.llm.rate_limiting.http_retry import (
    _CIRCUIT_BREAKER,
    _CIRCUIT_BREAKER_FAILURES,
    CIRCUIT_BREAKER_THRESHOLD,
    _DEFAULT_SSL_CONTEXT,
    APIStatusError,
    RateLimitError,
    _jitter_retry_after,
    _jittered_delay,
    _sanitize_url,
    fetch_with_retry,
    format_api_error_summary,
)

__all__ = [
    "APIStatusError",
    "RateLimitError",
    "fetch_with_retry",
    "format_api_error_summary",
    "_CIRCUIT_BREAKER",
    "_CIRCUIT_BREAKER_FAILURES",
    "CIRCUIT_BREAKER_THRESHOLD",
    "_DEFAULT_SSL_CONTEXT",
    "_jitter_retry_after",
    "_jittered_delay",
    "_sanitize_url",
]
