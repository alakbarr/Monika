"""
Monika Provider Subsystem.
Centralized LLM provider abstractions, credential pooling, error classification, and failover management.
"""

from provider.error_taxonomy import (
    FailoverReason,
    ErrorCategory,
    RecoveryAction,
    ClassifiedError,
    ErrorClassifier,
)
from provider.credential_pool import (
    CredentialPool,
    APICredentialPool,
    LLMCredentialPool,
    KeyHealth,
    CredentialState,
    get_credential_pool,
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
