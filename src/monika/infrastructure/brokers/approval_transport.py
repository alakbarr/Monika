# ==============================================================================
# File: infrastructure/brokers/approval_transport.py
# Backward-compatibility façade re-exporting domain approval transport primitives.
# ==============================================================================

"""
Approval Transport Façade.

Re-exports cryptographic approval payloads and canonical serialization functions
from monika.domain.risk.approval_transport for backward-compatibility.
"""

from __future__ import annotations

from monika.domain.risk.approval_transport import (
    ApprovalDecisionPayload,
    ApprovalRequestPayload,
    ApprovalTransport,
    canonical_json,
    compute_sha256_digest,
)

__all__ = [
    "canonical_json",
    "compute_sha256_digest",
    "ApprovalRequestPayload",
    "ApprovalDecisionPayload",
    "ApprovalTransport",
]
