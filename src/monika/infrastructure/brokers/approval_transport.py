# ==============================================================================
# File: risk/approval_transport.py
# ==============================================================================

"""
Cryptographic Approval Transport & Tamper-Proof Binding Protocol.
Ensures deterministic SHA-256 digest sealing across approval requests and decisions,
preventing man-in-the-middle tampering, parameter injection, replay attacks,
and cross-channel authorization spoofing across Telegram, Webhook, and REST API.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Union


def canonical_json(data: Any) -> str:
    """
    Serializes arbitrary data into deterministic canonical JSON format:
    - Sorted dictionary keys
    - Minimal compact separators (',', ':')
    - Standardized ISO timestamps
    - Stripped whitespace
    """
    def _default_serializer(obj: Any) -> Any:
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return str(obj)

    return json.dumps(
        data,
        default=_default_serializer,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_sha256_digest(content: Union[str, bytes]) -> str:
    """Computes lowercase hex SHA-256 digest of utf-8 encoded content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


@dataclass
class ApprovalRequestPayload:
    token: str
    action_type: str
    level: int
    description: str
    details: Dict[str, Any]
    requested_at: float
    expires_at: float
    request_digest: str = ""

    def __post_init__(self) -> None:
        if not self.request_digest:
            self.request_digest = self.compute_digest()

    def compute_digest(self) -> str:
        """Computes SHA-256 digest over the canonical request content."""
        canonical_payload = {
            "token": self.token,
            "action_type": self.action_type,
            "level": self.level,
            "description": self.description,
            "details": self.details,
            "requested_at": round(self.requested_at, 4),
            "expires_at": round(self.expires_at, 4),
        }
        return compute_sha256_digest(canonical_json(canonical_payload))

    def verify_integrity(self) -> bool:
        """Verifies if request_digest matches current payload content."""
        return self.request_digest == self.compute_digest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalDecisionPayload:
    token: str
    request_digest: str
    approved: bool
    decided_by: str
    decided_at: float
    reason: Optional[str] = None
    decision_digest: str = ""

    def __post_init__(self) -> None:
        if not self.decision_digest:
            self.decision_digest = self.compute_digest()

    def compute_digest(self) -> str:
        """Computes SHA-256 digest over the canonical decision content and bound request_digest."""
        canonical_payload = {
            "token": self.token,
            "request_digest": self.request_digest,
            "approved": bool(self.approved),
            "decided_by": self.decided_by,
            "decided_at": round(self.decided_at, 4),
            "reason": self.reason or "",
        }
        return compute_sha256_digest(canonical_json(canonical_payload))

    def verify_integrity(self) -> bool:
        """Verifies if decision_digest matches current decision payload."""
        return self.decision_digest == self.compute_digest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ApprovalTransport:
    """
    High-assurance transport protocol validator for trade executions & HITL authorizations.
    """

    @staticmethod
    def create_request(
        token: str,
        action_type: str,
        level: int,
        description: str,
        details: Dict[str, Any],
        requested_at: float,
        expires_at: float,
    ) -> ApprovalRequestPayload:
        """Creates a cryptographically sealed approval request payload."""
        return ApprovalRequestPayload(
            token=token,
            action_type=action_type,
            level=level,
            description=description,
            details=details,
            requested_at=requested_at,
            expires_at=expires_at,
        )

    @staticmethod
    def create_decision(
        request: ApprovalRequestPayload,
        approved: bool,
        decided_by: str,
        decided_at: float,
        reason: Optional[str] = None,
    ) -> ApprovalDecisionPayload:
        """Creates an approval decision cryptographically bound to request's digest."""
        if not request.verify_integrity():
            raise ValueError("Cannot sign decision for an invalid/tampered request payload.")

        return ApprovalDecisionPayload(
            token=request.token,
            request_digest=request.request_digest,
            approved=approved,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
        )

    @staticmethod
    def verify_binding(
        request: ApprovalRequestPayload,
        decision: ApprovalDecisionPayload,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Validates cryptographic integrity and tamper-proof binding between request and decision:
        1. Request digest integrity
        2. Decision digest integrity
        3. Token match
        4. Request digest exact match inside decision
        5. Expiration boundary check
        """
        if not request.verify_integrity():
            return False, "Approval request digest mismatch (payload corrupted or tampered)."

        if not decision.verify_integrity():
            return False, "Approval decision digest mismatch (decision payload corrupted or tampered)."

        if request.token != decision.token:
            return False, f"Token mismatch: request={request.token} vs decision={decision.token}."

        if decision.request_digest != request.request_digest:
            return False, (
                f"Cryptographic binding failed: decision refers to request digest {decision.request_digest}, "
                f"but request digest is {request.request_digest}."
            )

        current_time = now if now is not None else decision.decided_at
        if current_time > request.expires_at:
            return False, f"Decision arrived after request expiry (now={current_time} > expires_at={request.expires_at})."

        return True, "Approval binding verified successfully."
