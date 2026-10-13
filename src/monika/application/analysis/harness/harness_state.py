"""
Backward-compatibility facade for harness_state.
Canonical location: monika.application.agent.harness.harness_state
"""

import sys
import monika.application.agent.harness.harness_state as _canonical

from monika.application.agent.harness.harness_state import (
    HarnessState,
    PhaseAction,
    PhaseVerdict,
    SteeringMessage,
    evaluate_response_phase,
    handle_error_phase,
    prepare_turn_phase,
)

__all__ = [
    "HarnessState",
    "SteeringMessage",
    "PhaseAction",
    "PhaseVerdict",
    "prepare_turn_phase",
    "evaluate_response_phase",
    "handle_error_phase",
]

sys.modules[__name__] = _canonical
