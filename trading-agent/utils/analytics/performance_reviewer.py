"""
Compatibility facade shim for legacy performance_reviewer.py.
Re-exports from canonical monika.core.analytics.performance_reviewer.
"""

from __future__ import annotations

import monika.core.analytics.performance_reviewer as _canonical

from monika.core.analytics.performance_reviewer import (
    FUNDAMENTAL_PERFORMANCE_NOTES_PATH,
    PERFORMANCE_NOTES_PATH,
    analyze_failure_patterns,
    evaluate_candidate_lessons,
    generate_fundamental_performance_review,
    generate_weekly_review,
    should_regenerate_fundamental_notes,
)

__all__ = ['FUNDAMENTAL_PERFORMANCE_NOTES_PATH', 'PERFORMANCE_NOTES_PATH', 'analyze_failure_patterns', 'evaluate_candidate_lessons', 'generate_fundamental_performance_review', 'generate_weekly_review', 'should_regenerate_fundamental_notes']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
