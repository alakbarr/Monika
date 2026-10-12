"""
Compatibility facade shim for legacy specialist_tracker.py.
Re-exports from canonical monika.core.analytics.specialist_tracker.
"""

from __future__ import annotations

import monika.core.analytics.specialist_tracker as _canonical

from monika.core.analytics.specialist_tracker import (
    check_specialist_model_quality,
    compute_specialist_reliability,
)

__all__ = ['check_specialist_model_quality', 'compute_specialist_reliability']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
