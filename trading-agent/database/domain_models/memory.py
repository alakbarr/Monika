# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.memory
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.memory"""

import sys
import monika.infrastructure.database.domain_models.memory as _canonical

from monika.infrastructure.database.domain_models.memory import (
    CandidateLesson,
    ContextSpillBlob,
    DecisionMemory,
    DecisionReflection,
    MarketChronicle,
    UserMarketIntel,
)

sys.modules[__name__] = _canonical

__all__ = [
    "CandidateLesson",
    "ContextSpillBlob",
    "DecisionMemory",
    "DecisionReflection",
    "MarketChronicle",
    "UserMarketIntel",
]
