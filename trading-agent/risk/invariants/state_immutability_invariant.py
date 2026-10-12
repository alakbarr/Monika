# ==============================================================================
# File: risk/invariants/state_immutability_invariant.py
# Description: Backward-compatibility shim for monika.domain.risk.invariants.state_immutability_invariant
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.invariants.state_immutability_invariant
"""

import sys
import monika.domain.risk.invariants.state_immutability_invariant as _canonical

from monika.domain.risk.invariants.state_immutability_invariant import (
    InvariantViolationError,
    StateFreezeGuard,
    assert_state_immutability,
    compute_state_digest,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "InvariantViolationError",
    "StateFreezeGuard",
    "assert_state_immutability",
    "compute_state_digest",
    "logger",
]
