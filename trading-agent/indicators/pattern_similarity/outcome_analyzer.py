# ==============================================================================
# File: indicators/pattern_similarity/outcome_analyzer.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.outcome_analyzer
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.outcome_analyzer
"""

import sys
import monika.domain.indicators.pattern_similarity.outcome_analyzer as _canonical

from monika.domain.indicators.pattern_similarity.outcome_analyzer import (
    OutcomeAnalyzer,
    OutcomeStatistics,
    PatternMatch,
    PatternOutcome,
)

sys.modules[__name__] = _canonical

__all__ = [
    "OutcomeAnalyzer",
    "OutcomeStatistics",
    "PatternMatch",
    "PatternOutcome",
]
