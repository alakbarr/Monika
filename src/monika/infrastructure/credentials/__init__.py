"""
Monika Provider Subsystem.
Centralized LLM provider abstractions, credential pooling, error classification, and failover management.
"""

from monika.infrastructure.credentials.credential_pool import (
    APICredentialPool,
    CredentialPool,
    CredentialState,
    KeyHealth,
    LLMCredentialPool,
    get_credential_pool,
)
from monika.infrastructure.credentials.error_taxonomy import (
    ClassifiedError,
    ErrorCategory,
    ErrorClassifier,
    FailoverReason,
    RecoveryAction,
)

__all__ = [
    "FailoverReason",
    "ErrorCategory",
    "RecoveryAction",
    "ClassifiedError",
    "ErrorClassifier",
    "CredentialPool",
    "APICredentialPool",
    "LLMCredentialPool",
    "KeyHealth",
    "CredentialState",
    "get_credential_pool",
]
