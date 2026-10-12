"""
Compatibility facade shim for legacy credential_pool.py.
Re-exports from canonical monika.infrastructure.llm.credential_pool.
"""

from __future__ import annotations

import monika.infrastructure.llm.credential_pool as _canonical

from monika.infrastructure.llm.credential_pool import (
    CredentialState,
    LLMCredentialPool,
    CredentialPool,
)

__all__ = ['CredentialState', 'LLMCredentialPool', 'CredentialPool']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
