"""
Compatibility facade shim for legacy cftc_cot.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.cftc_cot.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.cftc_cot as _canonical

from monika.infrastructure.data_ingestion.sources.cftc_cot import (
    CFTCCOTFetcher,
    COMMODITY_CODES,
    DISAGGREGATED_DATASET,
    DISAGGREGATED_URL,
    FINANCIAL_DATASET,
    FINANCIAL_URL,
    _test,
    logger,
)

__all__ = ['CFTCCOTFetcher', 'COMMODITY_CODES', 'DISAGGREGATED_DATASET', 'DISAGGREGATED_URL', 'FINANCIAL_DATASET', 'FINANCIAL_URL', '_test', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
