# ==============================================================================
# File: risk/pending_action.py
# Description: Backward-compatibility shim for monika.domain.risk.pending_action
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.pending_action
"""

import sys
import monika.domain.risk.pending_action as _canonical

from monika.domain.risk.pending_action import (
    DEFAULT_PENDING_DIR,
    PendingAction,
    PendingActionManager,
    PendingActionStatus,
    annotations,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_PENDING_DIR",
    "PendingAction",
    "PendingActionManager",
    "PendingActionStatus",
    "annotations",
    "logger",
]
