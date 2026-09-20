"""
Unified Cross-Surface Approval Hub & Steering Bus.

Enforces unified Human-In-The-Loop (HITL) approvals across all interfaces:
Telegram Bot, Dashboard WebSockets, and TUI Terminal.

Key Capabilities:
1. Singleton event bus managing pending ApprovalRequests (trade tickets, risk overrides, emergency cuts).
2. Cross-surface synchronization: Once resolved (approved/rejected) on one surface,
   all other surfaces update instantly to prevent duplicate executions.
3. Handshake Hydration: Provides full snapshot of open requests when any surface reconnects.
4. Unified In-Flight Steering: Dispatches `/steer <symbol> <instruction>` to persistent storage
   and notifies all live listeners in real time.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.ApprovalHub")


@dataclass
class ApprovalRequest:
    request_id: str
    request_type: str  # "trade_proposal", "risk_override", "emergency_cut", "session_approval"
    symbol: str
    action: str  # "BUY", "SELL", "CLOSE", "ALLOW_SESSION"
    details: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # "pending", "approved", "rejected", "expired"
    operator: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return False


class ApprovalHub:
    """Unified singleton approval hub & steering event bus."""
    _instance: Optional[ApprovalHub] = None

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._listeners: List[Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]] = []
        self._execution_service = None

    @classmethod
    def get_instance(cls) -> ApprovalHub:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_execution_service(self, execution_service: Any) -> None:
        self._execution_service = execution_service

    def register_listener(self, callback: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        """Register an async callback for cross-surface event broadcasts."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def _broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast event to all registered UI listeners (WS, TG, TUI) and live feed."""
        for listener in list(self._listeners):
            try:
                await listener(event_type, data)
            except Exception as e:
                logger.debug(f"[ApprovalHub] Listener broadcast error: {e}")

        try:
            from logging_observability.dashboard.routes.common import broadcast_live_event
            await broadcast_live_event(event_type, data)
        except Exception:
            pass

    def create_request(
        self,
        request_id: str,
        symbol: str,
        action: str,
        request_type: str = "trade_proposal",
        details: Optional[Dict[str, Any]] = None,
        ttl_minutes: int = 15,
    ) -> ApprovalRequest:
        """Create and register a new pending approval request."""
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()
        req = ApprovalRequest(
            request_id=request_id,
            request_type=request_type,
            symbol=symbol.upper(),
            action=action.upper(),
            details=details or {},
            status="pending",
            created_at=now.isoformat(),
            expires_at=expires_at,
        )
        self._requests[request_id] = req
        logger.info(f"[ApprovalHub] Created approval request {request_id} for {action} {symbol}")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast("approval_requested", req.to_dict()))
        except RuntimeError:
            pass

        return req

    async def approve(self, request_id: str, operator: str = "operator") -> Tuple[bool, str]:
        """Approve a pending request across all surfaces."""
        req = self._requests.get(request_id)
        if not req:
            return False, f"Approval request '{request_id}' not found."

        if req.status != "pending":
            return False, f"Request '{request_id}' already resolved with status: {req.status} by {req.operator}."

        if req.is_expired:
            req.status = "expired"
            await self._broadcast("approval_resolved", req.to_dict())
            return False, f"Request '{request_id}' has expired."

        req.status = "approved"
        req.operator = operator
        logger.info(f"[ApprovalHub] Request {request_id} APPROVED by {operator}")

        exec_result_str = "Approved"
        analysis_id = req.details.get("analysis_id")
        if self._execution_service and analysis_id:
            try:
                res = await self._execution_service.execute_by_analysis_id(int(analysis_id))
                exec_result_str = res.summary() if hasattr(res, "summary") else str(res)
            except Exception as ex:
                logger.error(f"[ApprovalHub] Failed executing approved trade #{analysis_id}: {ex}")
                exec_result_str = f"Approved, but execution failed: {ex}"

        await self._broadcast("approval_resolved", {
            **req.to_dict(),
            "execution_result": exec_result_str,
        })
        return True, exec_result_str

    async def reject(self, request_id: str, operator: str = "operator", reason: str = "") -> Tuple[bool, str]:
        """Reject a pending request across all surfaces."""
        req = self._requests.get(request_id)
        if not req:
            return False, f"Approval request '{request_id}' not found."

        if req.status != "pending":
            return False, f"Request '{request_id}' already resolved with status: {req.status} by {req.operator}."

        req.status = "rejected"
        req.operator = operator
        req.rejection_reason = reason or "Rejected by operator"
        logger.info(f"[ApprovalHub] Request {request_id} REJECTED by {operator} (reason: {req.rejection_reason})")

        await self._broadcast("approval_resolved", req.to_dict())
        return True, f"Rejected by {operator}: {req.rejection_reason}"

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Fetch request by ID."""
        return self._requests.get(request_id)

    async def settle_expired_requests(self) -> List[ApprovalRequest]:
        """Auto-settles and broadcasts expired status for pending requests past their TTL."""
        expired = []
        for req in list(self._requests.values()):
            if req.status == "pending" and req.is_expired:
                req.status = "expired"
                expired.append(req)
                await self._broadcast("approval_settled_expired", req.to_dict())
                logger.info(f"[ApprovalHub] Auto-settled request {req.request_id} ({req.action} {req.symbol}) as EXPIRED.")
        return expired

    def get_open_requests(self) -> List[Dict[str, Any]]:
        """Return list of valid, unexpired pending requests for handshake hydration."""
        open_list = []
        for r in list(self._requests.values()):
            if r.status == "pending":
                if r.is_expired:
                    r.status = "expired"
                else:
                    open_list.append(r.to_dict())
        return open_list

    async def steer(
        self,
        symbol: str,
        instruction: str,
        operator: str = "operator",
    ) -> Dict[str, Any]:
        """
        Unified In-Flight Steering Dispatched across Telegram, Dashboard CRT, and TUI.
        """
        sym_clean = symbol.upper().strip() if symbol else "ALL"
        clean_inst = instruction.strip()

        try:
            from database.db import AsyncSessionLocal
            from database.models import UserMarketIntel, ActivityLog, _utcnow
            now = _utcnow()
            async with AsyncSessionLocal() as db_sess:
                db_sess.add(UserMarketIntel(
                    telegram_user_id=operator,
                    intel_type="tactical_directive",
                    title=f"Steer Directive ({sym_clean})",
                    summary=clean_inst,
                    directive="neutral",
                    target_cycle="continuous",
                    affected_symbols=sym_clean,
                    is_active=True,
                    created_at=now,
                ))
                db_sess.add(ActivityLog(
                    category="analysis",
                    description=f"Steer Directive injected for {sym_clean} by {operator}: {clean_inst[:150]}",
                    actor=operator,
                ))
                await db_sess.commit()
        except Exception as e:
            logger.warning(f"[ApprovalHub] Failed persisting steer directive to DB: {e}")

        steer_payload = {
            "symbol": sym_clean,
            "instruction": clean_inst,
            "operator": operator,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._broadcast("steer_injected", steer_payload)
        logger.info(f"[ApprovalHub] Steer synchronized across all surfaces for {sym_clean}: {clean_inst}")
        return steer_payload
