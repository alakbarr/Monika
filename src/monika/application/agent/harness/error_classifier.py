"""
Structured error classification and recovery strategy assignment (Phase 3).
Re-exports unified taxonomy from `provider.error_taxonomy`.
"""

from monika.infrastructure.credentials.error_taxonomy import (
    ClassifiedError,
    ErrorCategory,
    ErrorClassifier,
    FailoverReason,
    RecoveryAction,
    _extract_retry_after,
    fallback_multimodal_to_text,
    sanitize_unicode_surrogates,
)

__all__ = [
    "FailoverReason",
    "ErrorCategory",
    "RecoveryAction",
    "ClassifiedError",
    "ErrorClassifier",
    "sanitize_unicode_surrogates",
    "fallback_multimodal_to_text",
    "_extract_retry_after",
]
