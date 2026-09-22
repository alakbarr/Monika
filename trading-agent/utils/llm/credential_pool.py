"""
Multi-provider Credential Pooling and Automatic Rotation (Phase 8 - I7 & Monika v2).
Re-exports LLMCredentialPool and CredentialState from `provider.credential_pool`.
"""

from provider.credential_pool import (
    CredentialState,
    LLMCredentialPool,
)

# Backward-compatibility alias
CredentialPool = LLMCredentialPool

__all__ = [
    "CredentialState",
    "LLMCredentialPool",
    "CredentialPool",
]
