# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.analysis
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.analysis"""

import sys
import monika.infrastructure.database.domain_models.analysis as _canonical

from monika.infrastructure.database.domain_models.analysis import (
    AssetAnalysis,
    ConfluenceFactorOutcome,
    CyclePerformance,
    FundamentalBrief,
    PlaybookRuleAttribution,
    PrescreenLog,
    TimesFMForecast,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AssetAnalysis",
    "ConfluenceFactorOutcome",
    "CyclePerformance",
    "FundamentalBrief",
    "PlaybookRuleAttribution",
    "PrescreenLog",
    "TimesFMForecast",
]
