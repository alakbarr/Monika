"""
Structured error classification and recovery strategy assignment (Phase 3 & Monika v2).
Re-exports unified taxonomy from `provider.error_taxonomy`.
"""

from provider.error_taxonomy import (
    FailoverReason,
    ErrorCategory,
    RecoveryAction,
    ClassifiedError,
    ErrorClassifier,
    sanitize_unicode_surrogates,
    fallback_multimodal_to_text,
    _extract_retry_after,
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
