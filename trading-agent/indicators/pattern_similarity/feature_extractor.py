# ==============================================================================
# File: indicators/pattern_similarity/feature_extractor.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.feature_extractor
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.feature_extractor
"""

import sys
import monika.domain.indicators.pattern_similarity.feature_extractor as _canonical

from monika.domain.indicators.pattern_similarity.feature_extractor import (
    FeatureExtractor,
    FeatureVector,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FeatureExtractor",
    "FeatureVector",
]
