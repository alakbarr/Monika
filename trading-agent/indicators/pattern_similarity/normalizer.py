# ==============================================================================
# File: indicators/pattern_similarity/normalizer.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.normalizer
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.normalizer
"""

import sys
import monika.domain.indicators.pattern_similarity.normalizer as _canonical

from monika.domain.indicators.pattern_similarity.normalizer import (
    PriceNormalizer,
)

sys.modules[__name__] = _canonical

__all__ = [
    "PriceNormalizer",
]
