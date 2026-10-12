# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.news
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.news"""

import sys
import monika.infrastructure.database.domain_models.news as _canonical

from monika.infrastructure.database.domain_models.news import (
    EconomicCalendar,
    NewsClassificationOutcome,
    NewsDigest,
    NewsDigestSlice,
    NewsItem,
)

sys.modules[__name__] = _canonical

__all__ = [
    "EconomicCalendar",
    "NewsClassificationOutcome",
    "NewsDigest",
    "NewsDigestSlice",
    "NewsItem",
]
