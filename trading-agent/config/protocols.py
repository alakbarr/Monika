"""
Compatibility facade shim for legacy protocols.py.
Re-exports from canonical monika.core.config.protocols.
"""

from __future__ import annotations

import monika.core.config.protocols as _canonical

from monika.core.config.protocols import (
    CredentialResolver,
    notify_config_listeners,
    register_config_listener,
)

__all__ = ['CredentialResolver', 'notify_config_listeners', 'register_config_listener']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
