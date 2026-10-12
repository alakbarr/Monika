# ==============================================================================
# File: indicators/pattern_similarity/scanner.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.scanner
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.scanner
"""

import sys
import monika.domain.indicators.pattern_similarity.scanner as _canonical

from monika.domain.indicators.pattern_similarity.scanner import (
    PatternMatch,
    PriceNormalizer,
    SimilarityScanner,
)

sys.modules[__name__] = _canonical

__all__ = [
    "PatternMatch",
    "PriceNormalizer",
    "SimilarityScanner",
]
