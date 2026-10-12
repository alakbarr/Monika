# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.credentials
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.credentials"""

import sys
import monika.infrastructure.credentials as _canonical

from monika.infrastructure.credentials import (
    APICredentialPool,
    ClassifiedError,
    CredentialPool,
    CredentialState,
    ErrorCategory,
    ErrorClassifier,
    FailoverReason,
    KeyHealth,
    LLMCredentialPool,
    RecoveryAction,
    get_credential_pool,
)

__all__ = [
    "APICredentialPool",
    "ClassifiedError",
    "CredentialPool",
    "CredentialState",
    "ErrorCategory",
    "ErrorClassifier",
    "FailoverReason",
    "KeyHealth",
    "LLMCredentialPool",
    "RecoveryAction",
    "get_credential_pool",
]
