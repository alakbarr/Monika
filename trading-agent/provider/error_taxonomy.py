# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.credentials.error_taxonomy
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.credentials.error_taxonomy"""

import sys
import monika.infrastructure.credentials.error_taxonomy as _canonical

from monika.infrastructure.credentials.error_taxonomy import (
    ClassifiedError,
    ErrorCategory,
    ErrorClassifier,
    FailoverReason,
    RecoveryAction,
    SURROGATE_PATTERN,
    _COMPLETION_CEILING_PATTERNS,
    _HARD_QUOTA_PATTERNS,
    _OVERFLOW_PATTERNS,
    _extract_retry_after,
    fallback_multimodal_to_text,
    logger,
    sanitize_unicode_surrogates,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ClassifiedError",
    "ErrorCategory",
    "ErrorClassifier",
    "FailoverReason",
    "RecoveryAction",
    "SURROGATE_PATTERN",
    "_COMPLETION_CEILING_PATTERNS",
    "_HARD_QUOTA_PATTERNS",
    "_OVERFLOW_PATTERNS",
    "_extract_retry_after",
    "fallback_multimodal_to_text",
    "logger",
    "sanitize_unicode_surrogates",
]
