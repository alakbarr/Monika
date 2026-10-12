"""
Compatibility facade shim for legacy confidence_calibrator.py.
Re-exports from canonical monika.core.calibration.confidence_calibrator.
"""

from __future__ import annotations

import monika.core.calibration.confidence_calibrator as _canonical

from monika.core.calibration.confidence_calibrator import (
    apply_calibration_correction,
    calibrate_probability,
    compute_confidence_calibration,
    fit_isotonic_pav,
    fit_platt_scaling,
    get_calibrated_confidence,
)

__all__ = ['apply_calibration_correction', 'calibrate_probability', 'compute_confidence_calibration', 'fit_isotonic_pav', 'fit_platt_scaling', 'get_calibrated_confidence']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
