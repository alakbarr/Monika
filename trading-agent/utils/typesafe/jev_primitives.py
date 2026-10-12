"""
Compatibility facade shim for legacy jev_primitives.py.
Re-exports from canonical monika.core.primitives.jev_primitives.
"""

from __future__ import annotations

import monika.core.primitives.jev_primitives as _canonical

from monika.core.primitives.jev_primitives import (
    build_adjudication_questions,
    build_adversarial_check_questions,
    build_confluence_gate_questions,
    build_debate_evaluator_questions,
    build_digest_consistency_questions,
    build_exit_review_prescreen,
    build_fundamental_verifier_questions,
    build_news_classification_questions,
    build_news_classification_verify_questions,
    build_pattern_context_questions,
    build_position_guard_questions,
    build_prescreen_questions,
    build_realtime_news_questions,
    build_risk_gate_aggressive_questions,
    build_risk_gate_conservative_questions,
    build_risk_gate_neutral_questions,
    build_scenario_branch_questions,
    build_session_timing_questions,
    build_shadow_check_questions,
    build_telegram_intent_questions,
    classify_news_batch_with_jev,
    is_high_confidence,
    jev_questions_to_schema,
    list_to_jev_questions,
    logger,
    parse_jev_response_to_dict,
    schema_to_jev_questions,
)

__all__ = ['build_adjudication_questions', 'build_adversarial_check_questions', 'build_confluence_gate_questions', 'build_debate_evaluator_questions', 'build_digest_consistency_questions', 'build_exit_review_prescreen', 'build_fundamental_verifier_questions', 'build_news_classification_questions', 'build_news_classification_verify_questions', 'build_pattern_context_questions', 'build_position_guard_questions', 'build_prescreen_questions', 'build_realtime_news_questions', 'build_risk_gate_aggressive_questions', 'build_risk_gate_conservative_questions', 'build_risk_gate_neutral_questions', 'build_scenario_branch_questions', 'build_session_timing_questions', 'build_shadow_check_questions', 'build_telegram_intent_questions', 'classify_news_batch_with_jev', 'is_high_confidence', 'jev_questions_to_schema', 'list_to_jev_questions', 'logger', 'parse_jev_response_to_dict', 'schema_to_jev_questions']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
