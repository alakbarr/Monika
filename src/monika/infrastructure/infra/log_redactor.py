"""
Compatibility facade for canonical log redactor.
Re-exports all symbols from monika.core.security.log_redactor.
"""

import sys
import monika.core.security.log_redactor as _canonical

from monika.core.security.log_redactor import (
    REDACTION_PATTERNS,
    RedactingFormatter,
    SensitiveDataFilter,
    redact_sensitive_text,
)

__all__ = [
    "REDACTION_PATTERNS",
    "redact_sensitive_text",
    "SensitiveDataFilter",
    "RedactingFormatter",
]

sys.modules[__name__] = _canonical
