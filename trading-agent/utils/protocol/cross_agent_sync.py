"""
Compatibility facade shim for legacy cross_agent_sync.py.
Re-exports from canonical monika.application.protocol.cross_agent_sync.
"""

from __future__ import annotations

import monika.application.protocol.cross_agent_sync as _canonical

from monika.application.protocol.cross_agent_sync import (
    CrossAgentSynchronizer,
    PAIR_CORRELATIONS,
)

__all__ = ['CrossAgentSynchronizer', 'PAIR_CORRELATIONS']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
