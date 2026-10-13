"""
Backward-compatibility facade for error_classifier.
Canonical location: monika.application.agent.harness.error_classifier
"""

import sys
import monika.application.agent.harness.error_classifier as _canonical

from monika.application.agent.harness.error_classifier import (
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

sys.modules[__name__] = _canonical
