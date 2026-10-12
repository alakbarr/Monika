"""
Compatibility facade shim for legacy leading_survey_fetcher.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.leading_survey_fetcher.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.leading_survey_fetcher as _canonical

from monika.infrastructure.data_ingestion.sources.leading_survey_fetcher import (
    LeadingSurveyFetcher,
    logger,
)

__all__ = ['LeadingSurveyFetcher', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
