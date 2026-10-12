# ==============================================================================
# File: indicators/alpha_zoo/meta.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.meta
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.meta
"""

import sys
import monika.domain.indicators.alpha_zoo.meta as _canonical

from monika.domain.indicators.alpha_zoo.meta import (
    AlphaCategory,
    AlphaDirection,
    AlphaMeta,
    annotations,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaCategory",
    "AlphaDirection",
    "AlphaMeta",
    "annotations",
]
