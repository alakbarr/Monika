"""
Compatibility facade shim for legacy news_impact_keywords.py.
Re-exports from canonical monika.domain.market.news_impact_keywords.
"""

from __future__ import annotations

import monika.domain.market.news_impact_keywords as _canonical

from monika.domain.market.news_impact_keywords import (
    DEESCALATION_KEYWORDS,
    GEOPOLITICAL_HOTSPOT_ENTITIES,
    GEOPOLITICAL_LEADERS,
    HIGH_IMPACT_KEYWORDS,
    REHASH_KEYWORDS,
    SHOCK_KEYWORDS,
)

__all__ = ['DEESCALATION_KEYWORDS', 'GEOPOLITICAL_HOTSPOT_ENTITIES', 'GEOPOLITICAL_LEADERS', 'HIGH_IMPACT_KEYWORDS', 'REHASH_KEYWORDS', 'SHOCK_KEYWORDS']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
