"""
File: execution/service/trade_confirm.py
Universal Human-In-The-Loop (HITL) Trade Confirmation Manager for Monika.
Enforces pop-before-execute pattern, single-use token guarantees, and pre-commit drift checks
to eliminate race conditions and double-fill risks across Telegram and Dashboard channels.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable, Awaitable, Tuple

logger = logging.getLogger("TradingAgent.TradeConfirm")


@dataclass
class PendingTradeAction:
    confirm_id: str
    action_type: str  # place_order, close_position, override_risk, emergency_kill
    description: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 90.0
    channel_origin: str = "telegram"  # telegram, dashboard, cli


class TradeConfirmManager:
    """Centralized HITL confirmation coordinator with atomic pop-before-execute."""

    _instance: Optional["TradeConfirmManager"] = None
    _pending_actions: Dict[str, PendingTradeAction] = {}

    @classmethod
    def get_instance(cls) -> "TradeConfirmManager":
        if cls._instance is None:
            cls._instance = TradeConfirmManager()
        return cls._instance

    def create_pending_action(
        self,
        action_type: str,
        description: str,
        payload: Dict[str, Any],
        ttl_seconds: float = 90.0,
        channel_origin: str = "telegram",
    ) -> PendingTradeAction:
        """Registers a high-risk trade action requiring operator confirmation."""
        confirm_id = str(uuid.uuid4())
        action = PendingTradeAction(
            confirm_id=confirm_id,
            action_type=action_type,
            description=description,
            payload=payload,
            ttl_seconds=ttl_seconds,
            channel_origin=channel_origin,
        )
        self._pending_actions[confirm_id] = action
        logger.info(f"Created pending action {confirm_id} [{action_type}]: {description} (TTL: {ttl_seconds}s)")

        # Cross-surface synchronization with ApprovalHub
        try:
            from risk.approval_hub import ApprovalHub
            sym = str(payload.get("symbol") or "ALL")
            ApprovalHub.get_instance().create_request(
                request_id=confirm_id,
                symbol=sym,
                action=action_type.upper(),
                request_type=action_type,
                details={"description": description, "channel_origin": channel_origin, **payload},
                ttl_minutes=max(1, int(round(ttl_seconds / 60.0))),
            )
        except Exception as hub_err:
            logger.debug(f"[TradeConfirmManager] ApprovalHub sync register error: {hub_err}")

        return action

    def get_action(self, confirm_id: str) -> Optional[PendingTradeAction]:
        """Retrieves an action if still valid within TTL."""
        action = self._pending_actions.get(confirm_id)
        if not action:
            return None

        # Cross-check with ApprovalHub state: if already resolved elsewhere, invalidate local
        try:
            from risk.approval_hub import ApprovalHub
            hub_req = ApprovalHub.get_instance()._requests.get(confirm_id)
            if hub_req and hub_req.status != "pending":
                self._pending_actions.pop(confirm_id, None)
                logger.info(f"Pending action {confirm_id} already resolved via ApprovalHub ({hub_req.status}).")
                return None
        except Exception:
            pass

        if time.time() - action.created_at > action.ttl_seconds:
            self._pending_actions.pop(confirm_id, None)
            logger.warning(f"Pending action {confirm_id} expired and was discarded.")
            try:
                from risk.approval_hub import ApprovalHub
                hub = ApprovalHub.get_instance()
                if confirm_id in hub._requests:
                    hub._requests[confirm_id].status = "expired"
            except Exception:
                pass
            return None
        return action

    async def execute_confirmed_action(
        self,
        confirm_id: str,
        handler: Callable[[Dict[str, Any]], Awaitable[Any]],
        pre_check: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Tuple[bool, str, Any]:
        """Atomically pops action before execution to guarantee zero double-fills.
        
        Returns:
            Tuple of (Success bool, Message str, Handler result or None)
        """
        # 1. Pop-before-execute: atomic extraction prevents double click race condition
        action = self._pending_actions.pop(confirm_id, None)
        if not action:
            return False, "Aksi tidak ditemukan atau sudah pernah dieksekusi.", None

        if time.time() - action.created_at > action.ttl_seconds:
            try:
                from risk.approval_hub import ApprovalHub
                hub = ApprovalHub.get_instance()
                if confirm_id in hub._requests:
                    hub._requests[confirm_id].status = "expired"
            except Exception:
                pass
            return False, f"Aksi kedaluwarsa (batas waktu {action.ttl_seconds} detik terlampaui).", None

        # 2. Pre-commit sanity check (e.g. price drift or margin)
        if pre_check is not None:
            try:
                is_valid = pre_check(action.payload)
                if not is_valid:
                    return False, "Pemeriksaan validitas pra-eksekusi (pre-commit check) gagal.", None
            except Exception as check_err:
                logger.error(f"Pre-commit check exception for {confirm_id}: {check_err}")
                return False, f"Pre-commit check error: {check_err}", None

        # 3. Execution handler dispatch
        try:
            logger.info(f"Executing confirmed action {confirm_id} [{action.action_type}]...")
            result = await handler(action.payload)
            # Sync approval to ApprovalHub
            try:
                from risk.approval_hub import ApprovalHub
                hub = ApprovalHub.get_instance()
                if confirm_id in hub._requests:
                    hub._requests[confirm_id].status = "approved"
                    hub._requests[confirm_id].operator = action.channel_origin
            except Exception:
                pass
            return True, f"Aksi '{action.description}' berhasil dieksekusi.", result
        except Exception as exec_err:
            logger.error(f"Execution error on confirmed action {confirm_id}: {exec_err}", exc_info=True)
            try:
                from risk.approval_hub import ApprovalHub
                hub = ApprovalHub.get_instance()
                if confirm_id in hub._requests:
                    hub._requests[confirm_id].status = "rejected"
                    hub._requests[confirm_id].rejection_reason = str(exec_err)
            except Exception:
                pass
            return False, f"Eksekusi gagal: {exec_err}", None

    def cancel_action(self, confirm_id: str) -> bool:
        """Explicitly cancels a pending action."""
        if confirm_id in self._pending_actions:
            self._pending_actions.pop(confirm_id, None)
            logger.info(f"Pending action {confirm_id} was cancelled by operator.")
            try:
                from risk.approval_hub import ApprovalHub
                hub = ApprovalHub.get_instance()
                if confirm_id in hub._requests:
                    hub._requests[confirm_id].status = "rejected"
                    hub._requests[confirm_id].rejection_reason = "Cancelled by operator"
            except Exception:
                pass
            return True
        return False

    def list_pending(self) -> Dict[str, PendingTradeAction]:
        """Returns non-expired pending actions."""
        now = time.time()
        valid = {}
        for cid, act in list(self._pending_actions.items()):
            if now - act.created_at <= act.ttl_seconds:
                valid[cid] = act
            else:
                self._pending_actions.pop(cid, None)
        return valid
