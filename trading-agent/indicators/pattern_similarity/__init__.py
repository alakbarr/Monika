# ==============================================================================
# File: indicators/pattern_similarity/__init__.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity
"""

import sys
import monika.domain.indicators.pattern_similarity as _canonical

from monika.domain.indicators.pattern_similarity import (
    ContextAnnotation,
    ContextScorer,
    ContextVerdict,
    FeatureExtractor,
    FeatureVector,
    MarketContext,
    MultiTimeframeScreeningResult,
    OutcomeAnalyzer,
    OutcomeStatistics,
    PatternContextVerifier,
    PatternMatch,
    PatternOutcome,
    PatternSimilarityEngine,
    PriceNormalizer,
    SimilarityScanner,
    SingleTimeframeResult,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ContextAnnotation",
    "ContextScorer",
    "ContextVerdict",
    "FeatureExtractor",
    "FeatureVector",
    "MarketContext",
    "MultiTimeframeScreeningResult",
    "OutcomeAnalyzer",
    "OutcomeStatistics",
    "PatternContextVerifier",
    "PatternMatch",
    "PatternOutcome",
    "PatternSimilarityEngine",
    "PriceNormalizer",
    "SimilarityScanner",
    "SingleTimeframeResult",
]
