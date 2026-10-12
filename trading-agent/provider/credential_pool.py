# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.credentials.credential_pool
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.credentials.credential_pool"""

import sys
import monika.infrastructure.credentials.credential_pool as _canonical

from monika.infrastructure.credentials.credential_pool import (
    APICredentialPool,
    CredentialPool,
    CredentialState,
    CredentialStatus,
    KeyHealth,
    LLMCredentialPool,
    _GLOBAL_CREDENTIAL_POOL,
    get_credential_pool,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "APICredentialPool",
    "CredentialPool",
    "CredentialState",
    "CredentialStatus",
    "KeyHealth",
    "LLMCredentialPool",
    "_GLOBAL_CREDENTIAL_POOL",
    "get_credential_pool",
    "logger",
]
