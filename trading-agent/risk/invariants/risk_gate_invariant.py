# ==============================================================================
# File: risk/invariants/risk_gate_invariant.py
# Description: Backward-compatibility shim for monika.domain.risk.invariants.risk_gate_invariant
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.invariants.risk_gate_invariant
"""

import sys
import monika.domain.risk.invariants.risk_gate_invariant as _canonical

from monika.domain.risk.invariants.risk_gate_invariant import (
    InvariantViolationError,
    assert_risk_gate_invariants,
    check_risk_gate_invariant,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "InvariantViolationError",
    "assert_risk_gate_invariants",
    "check_risk_gate_invariant",
    "logger",
]
