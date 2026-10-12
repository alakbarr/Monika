# ==============================================================================
# File: indicators/pattern_similarity/__init__.py
# ==============================================================================

"""
Context-Aware Historical Chart Pattern Similarity Screening Engine.
Multi-timeframe, cross-symbol pattern recognition and outcome forecasting.
"""

from .models import (
    PatternMatch,
    MarketContext,
    ContextAnnotation,
    ContextVerdict,
    PatternOutcome,
    OutcomeStatistics,
    SingleTimeframeResult,
    MultiTimeframeScreeningResult,
)
from .normalizer import PriceNormalizer
from .feature_extractor import FeatureExtractor, FeatureVector
from .scanner import SimilarityScanner
from .context_scorer import ContextScorer
from .context_verifier import PatternContextVerifier
from .outcome_analyzer import OutcomeAnalyzer
from .engine import PatternSimilarityEngine

__all__ = [
    "PatternMatch",
    "MarketContext",
    "ContextAnnotation",
    "ContextVerdict",
    "PatternOutcome",
    "OutcomeStatistics",
    "SingleTimeframeResult",
    "MultiTimeframeScreeningResult",
    "PriceNormalizer",
    "FeatureExtractor",
    "FeatureVector",
    "SimilarityScanner",
    "ContextScorer",
    "PatternContextVerifier",
    "OutcomeAnalyzer",
    "PatternSimilarityEngine",
]
