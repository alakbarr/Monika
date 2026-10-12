# ==============================================================================
# File: indicators/pattern_similarity/context_verifier.py
# Description: Backward-compatibility shim for monika.domain.indicators.pattern_similarity.context_verifier
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.pattern_similarity.context_verifier
"""

import sys
import monika.domain.indicators.pattern_similarity.context_verifier as _canonical

from monika.domain.indicators.pattern_similarity.context_verifier import (
    ContextVerdict,
    MarketContext,
    MultiTimeframeScreeningResult,
    PatternContextVerifier,
    PatternMatch,
    VERDICT_JSON_SCHEMA,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ContextVerdict",
    "MarketContext",
    "MultiTimeframeScreeningResult",
    "PatternContextVerifier",
    "PatternMatch",
    "VERDICT_JSON_SCHEMA",
    "logger",
]
