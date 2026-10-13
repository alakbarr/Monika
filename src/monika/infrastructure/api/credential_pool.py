"""
Backward-compatibility facade for credential_pool.
Canonical location: monika.infrastructure.llm.rate_limiting.credential_pool
"""

import sys
import monika.infrastructure.llm.rate_limiting.credential_pool as _canonical

from monika.infrastructure.llm.rate_limiting.credential_pool import (
    APICredentialPool,
    CredentialPool,
    KeyHealth,
    get_credential_pool,
)

__all__ = [
    "KeyHealth",
    "APICredentialPool",
    "CredentialPool",
    "get_credential_pool",
]

sys.modules[__name__] = _canonical
