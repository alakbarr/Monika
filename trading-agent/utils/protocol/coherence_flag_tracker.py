"""
Compatibility facade shim for legacy coherence_flag_tracker.py.
Re-exports from canonical monika.application.protocol.coherence_flag_tracker.
"""

from __future__ import annotations

import monika.application.protocol.coherence_flag_tracker as _canonical

from monika.application.protocol.coherence_flag_tracker import (
    compute_coherence_override_impact,
)

__all__ = ['compute_coherence_override_impact']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
