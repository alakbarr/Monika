# ==============================================================================
# File: indicators/pattern_similarity/engine.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.engine
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.engine
"""

import sys
import monika.domain.indicators.pattern_similarity.engine as _canonical

from monika.domain.indicators.pattern_similarity.engine import (
    ContextScorer,
    FeatureExtractor,
    MarketContext,
    MultiTimeframeScreeningResult,
    OutcomeAnalyzer,
    PatternContextVerifier,
    PatternMatch,
    PatternSimilarityEngine,
    PriceNormalizer,
    SimilarityScanner,
    SingleTimeframeResult,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ContextScorer",
    "FeatureExtractor",
    "MarketContext",
    "MultiTimeframeScreeningResult",
    "OutcomeAnalyzer",
    "PatternContextVerifier",
    "PatternMatch",
    "PatternSimilarityEngine",
    "PriceNormalizer",
    "SimilarityScanner",
    "SingleTimeframeResult",
    "logger",
]
