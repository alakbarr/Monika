"""
Compatibility facade shim for legacy cds_threshold_calibrator.py.
Re-exports from canonical monika.core.calibration.cds_threshold_calibrator.
"""

from __future__ import annotations

import monika.core.calibration.cds_threshold_calibrator as _canonical

from monika.core.calibration.cds_threshold_calibrator import (
    CALIBRATION_INTERVAL_HOURS,
    CALIBRATION_KEY,
    MIN_TRADES_FOR_CALIBRATION,
    run_calibration_if_due,
)

__all__ = ['CALIBRATION_INTERVAL_HOURS', 'CALIBRATION_KEY', 'MIN_TRADES_FOR_CALIBRATION', 'run_calibration_if_due']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
