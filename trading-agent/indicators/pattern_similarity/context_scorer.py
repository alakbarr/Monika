# ==============================================================================
# File: indicators/pattern_similarity/context_scorer.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.context_scorer
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.context_scorer
"""

import sys
import monika.domain.indicators.pattern_similarity.context_scorer as _canonical

from monika.domain.indicators.pattern_similarity.context_scorer import (
    ContextAnnotation,
    ContextScorer,
    MarketContext,
    PatternMatch,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ContextAnnotation",
    "ContextScorer",
    "MarketContext",
    "PatternMatch",
    "logger",
]
