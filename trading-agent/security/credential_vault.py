"""
Compatibility facade shim for legacy credential_vault.py.
Re-exports from canonical monika.core.security.credential_vault.
"""

from __future__ import annotations

import monika.core.security.credential_vault as _canonical

from monika.core.security.credential_vault import (
    CredentialVault,
    SECRET_PATTERNS,
    SensitiveMaskingFilter,
    create_opaque_handle,
    delete_secret,
    get_secret,
    logger,
    mask_sensitive,
    resolve_opaque_handle,
    set_secret,
    vault,
)

__all__ = ['CredentialVault', 'SECRET_PATTERNS', 'SensitiveMaskingFilter', 'create_opaque_handle', 'delete_secret', 'get_secret', 'logger', 'mask_sensitive', 'resolve_opaque_handle', 'set_secret', 'vault']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
