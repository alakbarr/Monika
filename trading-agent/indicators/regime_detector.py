# ==============================================================================
# File: indicators/regime_detector.py
# Description: Backward-compatibility shim for monika.domain.indicators.regime_detector
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.regime_detector
"""

import sys
import monika.domain.indicators.regime_detector as _canonical

from monika.domain.indicators.regime_detector import (
    RegimeState,
    SchmittRegimeDetector,
    _GLOBAL_SCHMITT_DETECTOR,
    get_schmitt_regime_detector,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "RegimeState",
    "SchmittRegimeDetector",
    "_GLOBAL_SCHMITT_DETECTOR",
    "get_schmitt_regime_detector",
    "logger",
]
