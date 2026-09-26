# ==============================================================================
# File: risk/approval_hub.py
# ==============================================================================

"""
Human-in-the-Loop (HITL) Interactive Approval Hub & 4-Tier Security Gate.
Safeguards execution of high-risk trading orders, terminal commands,
and system-level interventions via interactive confirmation cards.

Approval Hierarchy:
  - Level 0 (INFO): Read-only queries, market quotes, status checks -> Auto-approved.
  - Level 1 (STANDARD): Standard algorithmic trades within risk thresholds -> Auto-approved with activity log.
  - Level 2 (SENSITIVE): Large position sizes, parameter overrides, shell commands -> Requires HITL confirmation card.
  - Level 3 (CRITICAL): Kill-switch activations, emergency account halts, database mutations -> Mandatory explicit admin confirmation with strict timeout.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Risk.ApprovalHub")

DEFAULT_APPROVAL_TTL = 300.0  # 5 minutes


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class ApprovalRequest:
    token: str
    level: int
    action_type: str
    description: str
    details: Dict[str, Any]
    requested_at: float
    expires_at: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None


class ApprovalHub:
    """
    Coordinates interactive human approval workflows across Telegram, Web Dashboard, and API.
    """

    def __init__(self, default_ttl: float = DEFAULT_APPROVAL_TTL):
        self.default_ttl = default_ttl
        self._requests: Dict[str, ApprovalRequest] = {}
        self._pending_futures: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def request_approval(
        self,
        action_type: str,
        level: int,
        description: str,
        details: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> ApprovalRequest:
        """
        Creates a new approval request. For Level 0 and 1, automatically approves.
        For Level 2 and 3, creates an interactive approval card.
        """
        token = f"appr_{int(time.time())}_{os.urandom(4).hex()}"
        now = time.time()
        ttl = ttl_seconds or self.default_ttl
        details_dict = details or {}

        # Auto-approve levels 0 and 1
        if level <= 1:
            req = ApprovalRequest(
                token=token,
                level=level,
                action_type=action_type,
                description=description,
                details=details_dict,
                requested_at=now,
                expires_at=now + ttl,
                status=ApprovalStatus.APPROVED,
                decided_by="system_auto_guard",
                decision_reason=f"Level {level} automatically authorized by risk policy.",
            )
            self._requests[token] = req
            logger.info(f"[ApprovalHub] Level {level} action '{action_type}' auto-approved (token={token}).")
            return req

        req = ApprovalRequest(
            token=token,
            level=level,
            action_type=action_type,
            description=description,
            details=details_dict,
            requested_at=now,
            expires_at=now + ttl,
            status=ApprovalStatus.PENDING,
        )
        self._requests[token] = req
        logger.warning(
            f"[ApprovalHub] Level {level} action '{action_type}' requires human authorization! (token={token})"
        )
        return req

    async def await_decision(
        self,
        token: str,
        timeout_seconds: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Asynchronously waits for human operator approval or rejection.
        Returns (is_approved, explanation_message).
        """
        req = self._requests.get(token)
        if not req:
            return False, f"Approval token '{token}' not found."

        if req.status == ApprovalStatus.APPROVED:
            return True, req.decision_reason or "Action approved."
        if req.status == ApprovalStatus.REJECTED:
            return False, req.decision_reason or "Action rejected by operator."

        now = time.time()
        remaining_ttl = max(0.1, req.expires_at - now)
        wait_timeout = min(timeout_seconds or remaining_ttl, remaining_ttl)

        loop = asyncio.get_running_loop()
        async with self._lock:
            fut = loop.create_future()
            self._pending_futures[token] = fut

        try:
            result = await asyncio.wait_for(fut, timeout=wait_timeout)
            return result
        except asyncio.TimeoutError:
            async with self._lock:
                self._pending_futures.pop(token, None)
            req.status = ApprovalStatus.EXPIRED
            req.decision_reason = "Approval request timed out without operator response."
            logger.warning(f"[ApprovalHub] Request '{token}' expired after {wait_timeout}s.")
            return False, req.decision_reason

    def decide(
        self,
        token: str,
        approved: bool,
        user_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Resolves a pending approval card with operator's decision.
        """
        req = self._requests.get(token)
        if not req or req.status != ApprovalStatus.PENDING:
            return False

        now = time.time()
        if now > req.expires_at:
            req.status = ApprovalStatus.EXPIRED
            req.decision_reason = "Request expired prior to decision."
            return False

        req.decided_by = user_id
        if approved:
            req.status = ApprovalStatus.APPROVED
            req.decision_reason = reason or f"Approved by operator '{user_id}'."
        else:
            req.status = ApprovalStatus.REJECTED
            req.decision_reason = reason or f"Rejected by operator '{user_id}'."

        logger.info(f"[ApprovalHub] Token '{token}' marked as {req.status.value} by '{user_id}'.")

        # Resolve pending future if awaiting
        fut = self._pending_futures.pop(token, None)
        if fut and not fut.done():
            fut.set_result((approved, req.decision_reason))

        return True

    def format_card_markdown(self, token: str) -> str:
        """Renders GitHub-style alert markdown card for human review."""
        req = self._requests.get(token)
        if not req:
            return f"Approval request `{token}` not found."

        urgency_badge = "CRITICAL ACTION" if req.level >= 3 else "HIGH RISK ACTION"
        lines = [
            f"### [HITL GATE] {urgency_badge} (Level {req.level})",
            f"**Action**: `{req.action_type}`",
            f"**Description**: {req.description}",
            f"**Token**: `{req.token}`",
            f"**Expires**: <t:{int(req.expires_at)}:R>",
            "",
            "**Operation Details:**",
            "```json",
        ]
        import json
        lines.append(json.dumps(req.details, indent=2))
        lines.append("```")
        lines.append("")
        lines.append(f"*Reply with `/approve {req.token}` or `/reject {req.token}`*")
        return "\n".join(lines)

    def format_telegram_inline_keyboard(self, token: str) -> List[List[Dict[str, str]]]:
        """Generates inline keyboard markup buttons for Telegram bot."""
        return [
            [
                {"text": "Approve", "callback_data": f"appr_yes:{token}"},
                {"text": "Reject", "callback_data": f"appr_no:{token}"},
            ]
        ]


_global_approval_hub: Optional[ApprovalHub] = None

def get_approval_hub() -> ApprovalHub:
    global _global_approval_hub
    if _global_approval_hub is None:
        _global_approval_hub = ApprovalHub()
    return _global_approval_hub
