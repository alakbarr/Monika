"""
Compatibility facade shim for legacy operator_feedback.py.
Re-exports from canonical monika.core.telemetry.operator_feedback.
"""

from __future__ import annotations

import monika.core.telemetry.operator_feedback as _canonical

from monika.core.telemetry.operator_feedback import (
    AnalysisFeedback,
    OperatorFeedbackManager,
    get_operator_feedback_manager,
    logger,
)

__all__ = ['AnalysisFeedback', 'OperatorFeedbackManager', 'get_operator_feedback_manager', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
