"""
Compatibility facade shim for legacy prescreen_calibrator.py.
Re-exports from canonical monika.core.calibration.prescreen_calibrator.
"""

from __future__ import annotations

import monika.core.calibration.prescreen_calibrator as _canonical

from monika.core.calibration.prescreen_calibrator import (
    compute_prescreen_skip_quality,
    resolve_pending_prescreen_logs,
)

__all__ = ['compute_prescreen_skip_quality', 'resolve_pending_prescreen_logs']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
