"""
Compatibility facade shim for legacy analysis_tracker.py.
Re-exports from canonical monika.core.analytics.analysis_tracker.
"""

from __future__ import annotations

import monika.core.analytics.analysis_tracker as _canonical

from monika.core.analytics.analysis_tracker import (
    analyze_debate_impact,
    compute_analysis_quality_report,
    compute_and_persist_factor_point_overrides,
    compute_dynamic_factor_weights,
    compute_factor_effectiveness,
    compute_factor_weights_recommendation,
    compute_model_source_performance,
    detect_score_inflation,
    get_adaptive_threshold_hints,
    get_confluence_calibration_status,
    get_direction_accuracy_report,
    get_per_asset_bias_report,
)

__all__ = ['analyze_debate_impact', 'compute_analysis_quality_report', 'compute_and_persist_factor_point_overrides', 'compute_dynamic_factor_weights', 'compute_factor_effectiveness', 'compute_factor_weights_recommendation', 'compute_model_source_performance', 'detect_score_inflation', 'get_adaptive_threshold_hints', 'get_confluence_calibration_status', 'get_direction_accuracy_report', 'get_per_asset_bias_report']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
