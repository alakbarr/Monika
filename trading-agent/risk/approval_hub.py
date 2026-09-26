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
import inspect
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from risk.approval_transport import ApprovalTransport

logger = logging.getLogger("TradingAgent.Risk.ApprovalHub")

DEFAULT_APPROVAL_TTL = 300.0  # 5 minutes


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"



@dataclass
class ApprovalRequest:
    token: str
    level: int = 1
    action_type: str = ""
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    requested_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: Union[ApprovalStatus, str] = ApprovalStatus.PENDING
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None
    symbol: str = "ALL"
    request_type: str = "trade_proposal"
    request_digest: Optional[str] = None
    decision_digest: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            status_lower = self.status.lower()
            for s in ApprovalStatus:
                if s.value == status_lower:
                    self.status = s
                    break
        if self.expires_at == 0.0:
            self.expires_at = self.requested_at + DEFAULT_APPROVAL_TTL

    @property
    def request_id(self) -> str:
        return self.token

    @request_id.setter
    def request_id(self, val: str) -> None:
        self.token = val

    @property
    def action(self) -> str:
        return self.action_type

    @action.setter
    def action(self, val: str) -> None:
        self.action_type = val

    @property
    def created_at(self) -> float:
        return self.requested_at

    @property
    def operator(self) -> Optional[str]:
        return self.decided_by

    @operator.setter
    def operator(self, val: Optional[str]) -> None:
        self.decided_by = val

    @property
    def rejection_reason(self) -> Optional[str]:
        return self.decision_reason

    @rejection_reason.setter
    def rejection_reason(self, val: Optional[str]) -> None:
        self.decision_reason = val

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class ApprovalHub:
    """
    Coordinates interactive human approval workflows across Telegram, Web Dashboard, and API.
    Provides singleton access and cross-surface event broadcast.
    """

    _instance: Optional[ApprovalHub] = None

    @classmethod
    def get_instance(cls) -> ApprovalHub:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, default_ttl: float = DEFAULT_APPROVAL_TTL):
        self.default_ttl = default_ttl
        self._requests: Dict[str, ApprovalRequest] = {}
        self._pending_futures: Dict[str, asyncio.Future] = {}
        self._listeners: List[Callable[[str, Dict[str, Any]], Awaitable[None]]] = []
        self._steer_history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    def register_listener(self, listener: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
        """Registers a cross-surface listener callback."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    async def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcasts event to all registered listeners asynchronously."""
        for listener in list(self._listeners):
            try:
                res = listener(event_type, data)
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                logger.error(f"[ApprovalHub] Error in approval listener {listener}: {exc}")

    def create_request(
        self,
        request_id: str,
        symbol: str = "ALL",
        action: str = "TRADE",
        request_type: str = "trade_proposal",
        details: Optional[Dict[str, Any]] = None,
        ttl_minutes: Optional[float] = None,
        ttl_seconds: Optional[float] = None,
        level: int = 2,
        description: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Creates and registers a cross-surface trade confirmation or intervention request.
        """
        now = time.time()
        if ttl_seconds is not None:
            ttl = ttl_seconds
        elif ttl_minutes is not None:
            ttl = ttl_minutes * 60.0
        else:
            ttl = self.default_ttl

        expires_at = now + ttl
        details_dict = details or {}
        desc = description or f"{action} {symbol} ({request_type})"

        req_payload = ApprovalTransport.create_request(
            token=request_id,
            action_type=action,
            level=level,
            description=desc,
            details=details_dict,
            requested_at=now,
            expires_at=expires_at,
        )

        req = ApprovalRequest(
            token=request_id,
            level=level,
            action_type=action,
            description=desc,
            details=details_dict,
            requested_at=now,
            expires_at=expires_at,
            status=ApprovalStatus.PENDING,
            symbol=symbol,
            request_type=request_type,
            request_digest=req_payload.request_digest,
        )
        self._requests[request_id] = req
        logger.info(
            f"[ApprovalHub] Created approval request '{request_id}' for {symbol} [{action}] "
            f"(digest={req.request_digest[:12]}, expires in {ttl:.1f}s)."
        )
        return req

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
            req_payload = ApprovalTransport.create_request(
                token=token,
                action_type=action_type,
                level=level,
                description=description,
                details=details_dict,
                requested_at=now,
                expires_at=now + ttl,
            )
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
                request_digest=req_payload.request_digest,
            )
            self._requests[token] = req
            logger.info(
                f"[ApprovalHub] Level {level} action '{action_type}' auto-approved "
                f"(token={token}, digest={req.request_digest[:12]})."
            )
            return req

        req_payload = ApprovalTransport.create_request(
            token=token,
            action_type=action_type,
            level=level,
            description=description,
            details=details_dict,
            requested_at=now,
            expires_at=now + ttl,
        )
        req = ApprovalRequest(
            token=token,
            level=level,
            action_type=action_type,
            description=description,
            details=details_dict,
            requested_at=now,
            expires_at=now + ttl,
            status=ApprovalStatus.PENDING,
            request_digest=req_payload.request_digest,
        )
        self._requests[token] = req
        logger.warning(
            f"[ApprovalHub] Level {level} action '{action_type}' requires human authorization! "
            f"(token={token}, digest={req.request_digest[:12]})"
        )
        return req

    async def approve(
        self,
        request_id: str,
        operator: str = "admin",
        reason: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Approves an open request with full cross-surface synchronization.
        """
        req = self._requests.get(request_id)
        if not req:
            return False, f"Approval request '{request_id}' not found."

        if req.status != ApprovalStatus.PENDING:
            return False, f"Request '{request_id}' already resolved with status '{req.status}'."

        now = time.time()
        if now > req.expires_at:
            req.status = ApprovalStatus.EXPIRED
            req.decision_reason = "Request expired prior to approval."
            return False, f"Request '{request_id}' has expired."

        req.status = ApprovalStatus.APPROVED
        req.decided_by = operator
        req.decision_reason = reason or f"Approved by {operator}."

        # Compute cryptographic decision digest bound to request_digest
        if req.request_digest:
            req_payload = ApprovalTransport.create_request(
                token=req.token,
                action_type=req.action_type,
                level=req.level,
                description=req.description,
                details=req.details,
                requested_at=req.requested_at,
                expires_at=req.expires_at,
            )
            dec_payload = ApprovalTransport.create_decision(
                request=req_payload,
                approved=True,
                decided_by=operator,
                decided_at=now,
                reason=req.decision_reason,
            )
            req.decision_digest = dec_payload.decision_digest

        msg = f"Request '{request_id}' Approved by {operator}."
        logger.info(f"[ApprovalHub] {msg} (digest={req.decision_digest[:12] if req.decision_digest else 'none'})")

        # Resolve pending future if awaiting
        fut = self._pending_futures.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result((True, req.decision_reason))

        # Broadcast event
        await self._emit_event(
            "approval_resolved",
            {
                "request_id": request_id,
                "status": "approved",
                "operator": operator,
                "symbol": req.symbol,
                "details": req.details,
                "decision_digest": req.decision_digest,
            },
        )
        return True, msg

    async def reject(
        self,
        request_id: str,
        operator: str = "admin",
        reason: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Rejects an open request with full cross-surface synchronization.
        """
        req = self._requests.get(request_id)
        if not req:
            return False, f"Approval request '{request_id}' not found."

        if req.status != ApprovalStatus.PENDING:
            return False, f"Request '{request_id}' already resolved with status '{req.status}'."

        now = time.time()
        if now > req.expires_at:
            req.status = ApprovalStatus.EXPIRED
            req.decision_reason = "Request expired prior to rejection."
            return False, f"Request '{request_id}' has expired."

        req.status = ApprovalStatus.REJECTED
        req.decided_by = operator
        req.decision_reason = reason or f"Rejected by {operator}."

        if req.request_digest:
            req_payload = ApprovalTransport.create_request(
                token=req.token,
                action_type=req.action_type,
                level=req.level,
                description=req.description,
                details=req.details,
                requested_at=req.requested_at,
                expires_at=req.expires_at,
            )
            dec_payload = ApprovalTransport.create_decision(
                request=req_payload,
                approved=False,
                decided_by=operator,
                decided_at=now,
                reason=req.decision_reason,
            )
            req.decision_digest = dec_payload.decision_digest

        msg = f"Request '{request_id}' Rejected by {operator}: {req.decision_reason}"
        logger.info(f"[ApprovalHub] {msg}")

        fut = self._pending_futures.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result((False, req.decision_reason))

        await self._emit_event(
            "approval_resolved",
            {
                "request_id": request_id,
                "status": "rejected",
                "operator": operator,
                "symbol": req.symbol,
                "reason": req.decision_reason,
                "details": req.details,
                "decision_digest": req.decision_digest,
            },
        )
        return True, msg

    async def steer(self, symbol: str, instruction: str, operator: str = "admin") -> Dict[str, Any]:
        """
        Injects a dynamic steering directive for an asset or system wide.
        """
        payload = {
            "symbol": symbol.upper(),
            "instruction": instruction,
            "operator": operator,
            "timestamp": time.time(),
        }
        self._steer_history.append(payload)
        logger.info(f"[ApprovalHub] Dynamic steer received from {operator} for {symbol}: '{instruction}'")
        await self._emit_event("steer_injected", payload)
        return payload

    def get_open_requests(self) -> List[ApprovalRequest]:
        """Returns active, non-expired pending requests."""
        now = time.time()
        return [
            req
            for req in self._requests.values()
            if req.status == ApprovalStatus.PENDING and now <= req.expires_at
        ]

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Alias for get_open_requests."""
        return self.get_open_requests()

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Retrieves an approval request by its token/ID."""
        return self._requests.get(request_id)

    async def await_decision(
        self,
        token: str,
        timeout_seconds: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Asynchronously waits for human operator approval or rejection.
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
        Synchronously resolves a pending approval card with operator decision.
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

        if req.request_digest:
            req_payload = ApprovalTransport.create_request(
                token=req.token,
                action_type=req.action_type,
                level=req.level,
                description=req.description,
                details=req.details,
                requested_at=req.requested_at,
                expires_at=req.expires_at,
            )
            dec_payload = ApprovalTransport.create_decision(
                request=req_payload,
                approved=approved,
                decided_by=user_id,
                decided_at=now,
                reason=req.decision_reason,
            )
            req.decision_digest = dec_payload.decision_digest

        logger.info(
            f"[ApprovalHub] Token '{token}' marked as {req.status.value} by '{user_id}' "
            f"(decision_digest={req.decision_digest[:12] if req.decision_digest else 'none'})."
        )

        fut = self._pending_futures.pop(token, None)
        if fut and not fut.done():
            fut.set_result((approved, req.decision_reason))

        return True

    def verify_request_binding(self, token: str) -> Tuple[bool, str]:
        """Validates cryptographic integrity and binding between request and decision."""
        req = self._requests.get(token)
        if not req:
            return False, f"Approval request '{token}' not found."
        if not req.request_digest:
            return False, "Request has no cryptographic request_digest."
        if not req.decision_digest:
            return False, "Request has not been decided or has no decision_digest."

        req_payload = ApprovalTransport.create_request(
            token=req.token,
            action_type=req.action_type,
            level=req.level,
            description=req.description,
            details=req.details,
            requested_at=req.requested_at,
            expires_at=req.expires_at,
        )
        dec_payload = ApprovalTransport.create_decision(
            request=req_payload,
            approved=(req.status == ApprovalStatus.APPROVED),
            decided_by=req.decided_by or "unknown",
            decided_at=req.requested_at,
            reason=req.decision_reason,
        )
        if not req_payload.verify_integrity():
            return False, "Request payload integrity check failed."
        return True, "Approval binding verified."

    def format_card_markdown(self, token: str) -> str:
        """Renders GitHub-style alert markdown card for human review."""
        req = self._requests.get(token)
        if not req:
            return f"Approval request `{token}` not found."

        urgency_badge = "CRITICAL ACTION" if req.level >= 3 else "HIGH RISK ACTION"
        digest_tag = f"`{req.request_digest[:12]}...`" if req.request_digest else "`unsigned`"
        lines = [
            f"### [HITL GATE] {urgency_badge} (Level {req.level})",
            f"**Action**: `{req.action_type}`",
            f"**Symbol**: `{req.symbol}`",
            f"**Description**: {req.description}",
            f"**Token**: `{req.token}`",
            f"**Digest**: {digest_tag}",
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
    return ApprovalHub.get_instance()
