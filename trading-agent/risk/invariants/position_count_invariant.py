# ==============================================================================
# File: risk/invariants/position_count_invariant.py
# Description: Backward-compatibility shim for monika.domain.risk.invariants.position_count_invariant
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.invariants.position_count_invariant
"""

import sys
import monika.domain.risk.invariants.position_count_invariant as _canonical

from monika.domain.risk.invariants.position_count_invariant import (
    InvariantResult,
    InvariantStatus,
    InvariantViolationError,
    assert_position_count_invariant,
    check_position_count_invariant,
)

sys.modules[__name__] = _canonical

__all__ = [
    "InvariantResult",
    "InvariantStatus",
    "InvariantViolationError",
    "assert_position_count_invariant",
    "check_position_count_invariant",
]
