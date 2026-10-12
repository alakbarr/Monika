# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.safe_ops
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.safe_ops"""

import sys
import monika.infrastructure.database.safe_ops as _canonical

from monika.infrastructure.database.safe_ops import (
    T,
    _safe_expunge_all,
    logger,
    safe_commit,
    safe_db_op,
)

sys.modules[__name__] = _canonical

__all__ = [
    "T",
    "_safe_expunge_all",
    "logger",
    "safe_commit",
    "safe_db_op",
]
