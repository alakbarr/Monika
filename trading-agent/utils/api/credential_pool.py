"""
Compatibility facade shim for legacy credential_pool.py.
Re-exports from canonical monika.infrastructure.api.credential_pool.
"""

from __future__ import annotations

import monika.infrastructure.api.credential_pool as _canonical

from monika.infrastructure.api.credential_pool import (
    KeyHealth,
    APICredentialPool,
    CredentialPool,
    get_credential_pool,
)

__all__ = ['KeyHealth', 'APICredentialPool', 'CredentialPool', 'get_credential_pool']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
