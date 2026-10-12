# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.audit_logger
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.audit_logger"""

import sys
import monika.infrastructure.brokers.audit_logger as _canonical

from monika.infrastructure.brokers.audit_logger import (
    TradeAuditLogger,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "TradeAuditLogger",
    "logger",
]
