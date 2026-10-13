# ==============================================================================
# File: indicators/pattern_similarity/__init__.py
# ==============================================================================

"""
Context-Aware Historical Chart Pattern Similarity Screening Engine.
Multi-timeframe, cross-symbol pattern recognition and outcome forecasting.
"""

from .context_scorer import ContextScorer
from .context_verifier import PatternContextVerifier
from .engine import PatternSimilarityEngine
from .feature_extractor import FeatureExtractor, FeatureVector
from .models import (
    ContextAnnotation,
    ContextVerdict,
    MarketContext,
    MultiTimeframeScreeningResult,
    OutcomeStatistics,
    PatternMatch,
    PatternOutcome,
    SingleTimeframeResult,
)
from .normalizer import PriceNormalizer
from .outcome_analyzer import OutcomeAnalyzer
from .scanner import SimilarityScanner

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
