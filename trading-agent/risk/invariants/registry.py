# ==============================================================================
# File: risk/invariants/registry.py
# Description: Backward-compatibility shim for monika.domain.risk.invariants.registry
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.invariants.registry
"""

import sys
import monika.domain.risk.invariants.registry as _canonical

from monika.domain.risk.invariants.registry import (
    InvariantRegistry,
    InvariantResult,
    InvariantStatus,
    InvariantViolationError,
    get_global_invariant_registry,
    logger,
    reset_global_invariant_registry,
)

sys.modules[__name__] = _canonical

__all__ = [
    "InvariantRegistry",
    "InvariantResult",
    "InvariantStatus",
    "InvariantViolationError",
    "get_global_invariant_registry",
    "logger",
    "reset_global_invariant_registry",
]
