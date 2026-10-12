# ==============================================================================
# File: risk/invariants/__init__.py
# Description: Backward-compatibility shim for monika.domain.risk.invariants
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.invariants
"""

import sys
import monika.domain.risk.invariants as _canonical

from monika.domain.risk.invariants import (
    InvariantRegistry,
    InvariantResult,
    InvariantStatus,
    InvariantViolationError,
    StateFreezeGuard,
    assert_position_count_invariant,
    assert_risk_gate_invariants,
    assert_state_immutability,
    check_position_count_invariant,
    check_risk_gate_invariant,
    get_global_invariant_registry,
    reset_global_invariant_registry,
)

sys.modules[__name__] = _canonical

__all__ = [
    "InvariantRegistry",
    "InvariantResult",
    "InvariantStatus",
    "InvariantViolationError",
    "StateFreezeGuard",
    "assert_position_count_invariant",
    "assert_risk_gate_invariants",
    "assert_state_immutability",
    "check_position_count_invariant",
    "check_risk_gate_invariant",
    "get_global_invariant_registry",
    "reset_global_invariant_registry",
]
