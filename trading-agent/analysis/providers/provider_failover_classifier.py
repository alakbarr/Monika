# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.provider_failover_classifier
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.provider_failover_classifier"""

import sys
import monika.infrastructure.providers.provider_failover_classifier as _canonical

from monika.infrastructure.providers.provider_failover_classifier import (
    FailoverReason,
    _AUTH_PATTERNS,
    _BILLING_PATTERNS,
    _COMPLETION_CEILING_PATTERNS,
    _CONN_PATTERNS,
    _ENTITLEMENT_PATTERNS,
    _FILTER_PATTERNS,
    _HARD_QUOTA_PATTERNS,
    _IMAGE_CORRUPT_PATTERNS,
    _IMAGE_LARGE_PATTERNS,
    _INVALID_REQ_PATTERNS,
    _MARGIN_PATTERNS,
    _NOT_FOUND_PATTERNS,
    _OVERFLOW_PATTERNS,
    _OVERLOAD_PATTERNS,
    _RATE_PATTERNS,
    _ROLE_ALT_PATTERNS,
    _SERVER_PATTERNS,
    _THINKING_PATTERNS,
    _TIMEOUT_PATTERNS,
    _UPSTREAM_RATE_PATTERNS,
    _WAF_PATTERNS,
    classify_error,
    extract_completion_ceiling,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FailoverReason",
    "_AUTH_PATTERNS",
    "_BILLING_PATTERNS",
    "_COMPLETION_CEILING_PATTERNS",
    "_CONN_PATTERNS",
    "_ENTITLEMENT_PATTERNS",
    "_FILTER_PATTERNS",
    "_HARD_QUOTA_PATTERNS",
    "_IMAGE_CORRUPT_PATTERNS",
    "_IMAGE_LARGE_PATTERNS",
    "_INVALID_REQ_PATTERNS",
    "_MARGIN_PATTERNS",
    "_NOT_FOUND_PATTERNS",
    "_OVERFLOW_PATTERNS",
    "_OVERLOAD_PATTERNS",
    "_RATE_PATTERNS",
    "_ROLE_ALT_PATTERNS",
    "_SERVER_PATTERNS",
    "_THINKING_PATTERNS",
    "_TIMEOUT_PATTERNS",
    "_UPSTREAM_RATE_PATTERNS",
    "_WAF_PATTERNS",
    "classify_error",
    "extract_completion_ceiling",
    "logger",
]

