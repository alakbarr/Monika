# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.idempotency_guard
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.idempotency_guard"""

import sys
import monika.infrastructure.brokers.idempotency_guard as _canonical

from monika.infrastructure.brokers.idempotency_guard import (
    IdempotencyGuard,
    IdempotencyRecord,
    IdempotencyState,
    _GLOBAL_IDEMPOTENCY_GUARD,
    get_idempotency_guard,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "IdempotencyGuard",
    "IdempotencyRecord",
    "IdempotencyState",
    "_GLOBAL_IDEMPOTENCY_GUARD",
    "get_idempotency_guard",
    "logger",
]
