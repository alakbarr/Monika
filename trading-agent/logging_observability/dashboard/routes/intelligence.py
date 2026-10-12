"""
Compatibility facade shim for legacy intelligence.py.
Re-exports from canonical monika.interfaces.dashboard.routes.intelligence.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.intelligence as _canonical

from monika.interfaces.dashboard.routes.intelligence import (
    crystallize_skills_now,
    curate_crystallized_skills,
    deprecate_crystallized_skill,
    get_aggregated_sentiment,
    get_calendar_events,
    get_classified_news,
    get_cot_reports,
    get_crystallized_skills,
    get_latest_tearsheet,
    get_market_fear_greed,
    get_market_fedwatch,
    get_market_sentiment_composite,
    get_market_yields,
    get_skill_stats,
    get_skills_catalog,
    get_upcoming_high_impact_events,
    intelligence_router,
    logger,
)

__all__ = ['crystallize_skills_now', 'curate_crystallized_skills', 'deprecate_crystallized_skill', 'get_aggregated_sentiment', 'get_calendar_events', 'get_classified_news', 'get_cot_reports', 'get_crystallized_skills', 'get_latest_tearsheet', 'get_market_fear_greed', 'get_market_fedwatch', 'get_market_sentiment_composite', 'get_market_yields', 'get_skill_stats', 'get_skills_catalog', 'get_upcoming_high_impact_events', 'intelligence_router', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
