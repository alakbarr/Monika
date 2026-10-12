# ==============================================================================
# File: execution/service/sizing_calculator.py
# Description: Backward-compatibility shim for monika.domain.execution.sizing_calculator
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.sizing_calculator
"""

import sys
import monika.domain.execution.sizing_calculator as _canonical

from monika.domain.execution.sizing_calculator import (
    SizingCalculator,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "SizingCalculator",
    "logger",
]
