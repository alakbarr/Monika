# ==============================================================================
# File: indicators/chart_patterns.py
# Description: Backward-compatibility shim for monika.domain.indicators.chart_patterns
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.chart_patterns
"""

import sys
import monika.domain.indicators.chart_patterns as _canonical

from monika.domain.indicators.chart_patterns import (
    detect_double_tops_bottoms,
    detect_harmonic_patterns,
    detect_head_and_shoulders,
    find_swing_pivots,
    logger,
    scan_all_chart_patterns,
)

sys.modules[__name__] = _canonical

__all__ = [
    "detect_double_tops_bottoms",
    "detect_harmonic_patterns",
    "detect_head_and_shoulders",
    "find_swing_pivots",
    "logger",
    "scan_all_chart_patterns",
]
