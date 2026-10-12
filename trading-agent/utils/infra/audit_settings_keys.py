"""
Compatibility facade shim for legacy audit_settings_keys.py.
Re-exports from canonical monika.infrastructure.infra.audit_settings_keys.
"""

from __future__ import annotations

import monika.infrastructure.infra.audit_settings_keys as _canonical

from monika.infrastructure.infra.audit_settings_keys import (
    audit_keys,
    flatten_dict,
)

__all__ = ['audit_keys', 'flatten_dict']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
