# ==============================================================================
# File: risk/approval_hub.py
# Description: Backward-compatibility shim for monika.domain.risk.approval_hub
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.approval_hub
"""

import sys
import monika.domain.risk.approval_hub as _canonical

from monika.domain.risk.approval_hub import (
    ApprovalHub,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalTransport,
    BoundedMandate,
    DEFAULT_APPROVAL_TTL,
    DEFAULT_MANDATE_TTL,
    _global_approval_hub,
    annotations,
    get_approval_hub,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ApprovalHub",
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalTransport",
    "BoundedMandate",
    "DEFAULT_APPROVAL_TTL",
    "DEFAULT_MANDATE_TTL",
    "_global_approval_hub",
    "annotations",
    "get_approval_hub",
    "logger",
]
