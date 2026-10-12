# ==============================================================================
# File: indicators/candlestick_patterns.py
# Description: Backward-compatibility shim for monika.domain.indicators.candlestick_patterns
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.candlestick_patterns
"""

import sys
import monika.domain.indicators.candlestick_patterns as _canonical

from monika.domain.indicators.candlestick_patterns import (
    detect_candlestick_patterns,
)

sys.modules[__name__] = _canonical

__all__ = [
    "detect_candlestick_patterns",
]
