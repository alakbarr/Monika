"""
Compatibility facade shim for legacy ssvp_coordinator.py.
Re-exports from canonical monika.application.protocol.ssvp_coordinator.
"""

from __future__ import annotations

import monika.application.protocol.ssvp_coordinator as _canonical

from monika.application.protocol.ssvp_coordinator import (
    SSVPCoordinator,
)

__all__ = ['SSVPCoordinator']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
