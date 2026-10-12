"""
Compatibility facade shim for legacy cot_thresholds.py.
Re-exports from canonical monika.core.calibration.cot_thresholds.
"""

from __future__ import annotations

import monika.core.calibration.cot_thresholds as _canonical

from monika.core.calibration.cot_thresholds import (
    cot_extreme_score,
    get_cot_extreme_thresholds,
)

__all__ = ['cot_extreme_score', 'get_cot_extreme_thresholds']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
