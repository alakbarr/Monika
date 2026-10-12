# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.approval_transport
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.approval_transport"""

import sys
import monika.infrastructure.brokers.approval_transport as _canonical

from monika.infrastructure.brokers.approval_transport import (
    ApprovalDecisionPayload,
    ApprovalRequestPayload,
    ApprovalTransport,
    canonical_json,
    compute_sha256_digest,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ApprovalDecisionPayload",
    "ApprovalRequestPayload",
    "ApprovalTransport",
    "canonical_json",
    "compute_sha256_digest",
]
