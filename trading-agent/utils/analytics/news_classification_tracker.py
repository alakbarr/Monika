"""
Compatibility facade shim for legacy news_classification_tracker.py.
Re-exports from canonical monika.core.analytics.news_classification_tracker.
"""

from __future__ import annotations

import monika.core.analytics.news_classification_tracker as _canonical

from monika.core.analytics.news_classification_tracker import (
    IMPACT_CURRENCY_SYMBOL_MAP,
    IMPACT_MOVE_THRESHOLDS_PCT,
    compute_and_apply_tier_calibration,
    compute_news_classification_calibration,
    resolve_pending_news_outcomes,
    snapshot_classification_for_tracking,
)

__all__ = ['IMPACT_CURRENCY_SYMBOL_MAP', 'IMPACT_MOVE_THRESHOLDS_PCT', 'compute_and_apply_tier_calibration', 'compute_news_classification_calibration', 'resolve_pending_news_outcomes', 'snapshot_classification_for_tracking']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
