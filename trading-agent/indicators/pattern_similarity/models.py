# ==============================================================================
# File: indicators/pattern_similarity/models.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.models
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.models
"""

import sys
import monika.domain.indicators.pattern_similarity.models as _canonical

from monika.domain.indicators.pattern_similarity.models import (
    ContextAnnotation,
    ContextVerdict,
    MarketContext,
    MultiTimeframeScreeningResult,
    OutcomeStatistics,
    PatternMatch,
    PatternOutcome,
    SingleTimeframeResult,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ContextAnnotation",
    "ContextVerdict",
    "MarketContext",
    "MultiTimeframeScreeningResult",
    "OutcomeStatistics",
    "PatternMatch",
    "PatternOutcome",
    "SingleTimeframeResult",
]
