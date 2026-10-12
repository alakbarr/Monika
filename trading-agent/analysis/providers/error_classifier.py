# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.error_classifier
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.error_classifier"""

import sys
import monika.infrastructure.providers.error_classifier as _canonical

from monika.infrastructure.providers.error_classifier import (
    FailoverReason,
    classify_error,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FailoverReason",
    "classify_error",
]
