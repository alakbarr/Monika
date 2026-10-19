# ==============================================================================
# File: application/agent/chat/action_state.py
# ==============================================================================

"""
PendingAction lifecycle, session approvals, proposal confirmation, and denial circuit breaker.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.db import get_session
import uuid
from monika.infrastructure.database.models import ActivityLog, TelegramConversation
from monika.application.agent.chat.base import _ChatAgentMixinBase, logger
from monika.application.agent.chat.pending_actions import PendingAction


class ActionStateMixin(_ChatAgentMixinBase):
    """Mixin managing pending action state, session approval gates, and confirmations."""

    def is_symbol_session_approved(self, symbol: str) -> bool:
        """Periksa apakah simbol memiliki izin approval aktif pada level sesi."""
        if not symbol:
            return False
        sym_clean = symbol.strip().upper().replace("/", "")
        expiry = self._session_approvals.get(sym_clean)
        if expiry is None:
            return False
        if datetime.now(timezone.utc) > expiry:
            del self._session_approvals[sym_clean]
            return False
        return True

    def add_session_approval(self, symbol: str) -> datetime:
        """Berikan izin sesi berdurasi 4 jam untuk simbol tertentu."""
        sym_clean = symbol.strip().upper().replace("/", "")
        expiry = datetime.now(timezone.utc) + timedelta(hours=self.SESSION_APPROVAL_TTL_HOURS)
        self._session_approvals[sym_clean] = expiry
        logger.info(
            f"[ChatAgent] Session approval granted for {sym_clean} "
            f"until {expiry.isoformat()} (TTL: {self.SESSION_APPROVAL_TTL_HOURS}h)"
        )
        return expiry

    async def _persist_pending_action(self, action: PendingAction):
        """Save pending action to SystemConfig table in DB."""
        try:
            from monika.infrastructure.database.models import SystemConfig

            async with get_session() as session:
                await SystemConfig.upsert(
                    session,
                    key=f"pending_action:{action.action_id}",
                    value=json.dumps(action.to_dict()),
                    description=f"Telegram pending action: {action.action_type}",
                )
                await session.commit()
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not persist pending action {action.action_id}: {e}")

    async def _delete_persisted_pending_action(self, action_id: str) -> None:
        """Remove persisted pending action from SystemConfig table."""
        try:
            from sqlalchemy import delete

            from monika.infrastructure.database.models import SystemConfig

            async with get_session() as session:
                await session.execute(delete(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}"))
                await session.commit()
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not delete persisted pending action {action_id}: {e}")

    async def _claim_persisted_pending_action(self, action_id: str) -> bool:
        """
        Atomically delete persisted pending action from SystemConfig table.
        Returns True only if this caller was the one that deleted the row (atomic claim).
        """
        try:
            from sqlalchemy import delete

            from monika.infrastructure.database.models import SystemConfig

            async with get_session() as session:
                res = await session.execute(
                    delete(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}")
                )
                await session.commit()
                rowcount = getattr(res, "rowcount", 0)
                return bool(rowcount and rowcount > 0)
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not atomically claim pending action {action_id}: {e}")
            return False

    async def get_pending_action(self, action_id: str) -> Optional[PendingAction]:
        """Fetch pending action from memory or restore from DB."""
        action = self._pending_actions.get(action_id)
        if action:
            return action
        try:
            from sqlalchemy import delete, select

            from monika.infrastructure.database.models import SystemConfig

            async with get_session() as session:
                cfg = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}"))
                ).scalar_one_or_none()
                if cfg and cfg.value:
                    data = json.loads(cfg.value)
                    restored = PendingAction.from_dict(data)
                    if not restored.is_expired():
                        self._pending_actions[action_id] = restored
                        return restored
                    else:
                        await session.execute(
                            delete(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}")
                        )
                        await session.commit()
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not restore pending action {action_id}: {e}")
        return None

    def _get_action_lock(self) -> asyncio.Lock:
        if not hasattr(self, "_action_lock") or self._action_lock is None:
            self._action_lock = asyncio.Lock()
        return self._action_lock

    async def approve_for_session(self, action_id: str) -> tuple[bool, str]:
        """Eksekusi aksi dan aktifkan approval sesi hanya jika eksekusi berhasil."""
        action = await self.get_pending_action(action_id)
        if not action:
            return False, "Action not found or already processed."
        symbol = str(action.params.get("symbol") or "")
        success, msg = await self.confirm_action(action_id)
        if success and symbol:
            self.add_session_approval(symbol)
            msg += (
                f"\n\n *Izin Sesi Aktif*: Sesi aktif untuk `{symbol.upper()}` "
                f"selama {self.SESSION_APPROVAL_TTL_HOURS} jam ke depan."
            )
        return success, msg

    def is_proposals_paused(self) -> bool:
        """Check if trading action proposals are currently paused by denial circuit breaker."""
        return self._proposals_paused

    def record_denial(self) -> tuple[bool, str]:
        """Record a denial; if consecutive denials reach threshold, trip circuit breaker."""
        self._consecutive_denials += 1
        if self._consecutive_denials >= self.DENIAL_BREAKER_THRESHOLD:
            self._proposals_paused = True
            return True, "Circuit breaker triggered: 3 consecutive denials. Auto-proposals paused."
        return False, f"Denial recorded ({self._consecutive_denials}/{self.DENIAL_BREAKER_THRESHOLD})."

    def resume_proposals(self) -> str:
        """Reset denial circuit breaker and re-enable action proposals."""
        self._consecutive_denials = 0
        self._proposals_paused = False
        return "Auto-proposals resumed. Agent may propose trading actions again."

    async def confirm_action(self, action_id: str) -> tuple[bool, str]:
        """
        Mengeksekusi usulan aksi setelah user konfirmasi.
        Dilindungi oleh lock konkurensi untuk mencegah eksekusi ganda (double-execution race).
        Returns: (success, message)
        """
        async with self._get_action_lock():
            action = await self.get_pending_action(action_id)
            if not action:
                return False, "Action not found or already processed."
            if action.is_expired():
                self._pending_actions.pop(action_id, None)
                await self._delete_persisted_pending_action(action_id)
                return False, "Action expired (90-second timeout). Please request again."

            # Pop immediately within the lock to claim exclusive ownership
            had_mem = self._pending_actions.pop(action_id, None) is not None
            claimed_db = await self._claim_persisted_pending_action(action_id)
            if not had_mem and not claimed_db:
                return False, "Action not found or already processed by another request."
            self._consecutive_denials = 0  # Reset on approval

        # Execute claimed action outside the lock to avoid blocking other actions
        try:
            result_msg = await self._execute_action(action)
            is_success = not result_msg.startswith("[GAGAL]") and not result_msg.startswith("[ERROR]")
            async with get_session() as session:
                session.add(
                    ActivityLog(
                        category="trading",
                        description=f"Telegram user {self.user_id} CONFIRMED: {action.description} → {result_msg}",
                        actor="telegram_chat_agent",
                    )
                )
                await session.commit()
            return is_success, result_msg
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False, f"Execution failed: {e}"

    async def reject_action(self, action_id: str) -> str:
        """Menghapus usulan aksi setelah user menolak."""
        action = await self.get_pending_action(action_id)
        if not action:
            return "Action not found."

        self._pending_actions.pop(action_id, None)
        await self._delete_persisted_pending_action(action_id)

        self._consecutive_denials += 1
        if self._consecutive_denials >= self.DENIAL_BREAKER_THRESHOLD:
            self._proposals_paused = True
            notice = (
                f"Action rejected: {action.description}\n\n"
                "[PERINGATAN] Circuit breaker tripped: 3 consecutive denials. "
                "Auto-proposals paused. Use /resume_proposals to re-enable."
            )
        else:
            notice = f"Action rejected: {action.description}"

        async with get_session() as session:
            session.add(
                ActivityLog(
                    category="trading",
                    description=f"Telegram user {self.user_id} REJECTED: {action.description} (consecutive_denials={self._consecutive_denials})",
                    actor="telegram_chat_agent",
                )
            )
            await session.commit()
        return notice

    def _create_pending_action(self, proposed: dict) -> Optional[PendingAction]:
        """Ubah call PROPOSE_ACTION dari AI menjadi objek PendingAction."""
        if self._proposals_paused:
            logger.warning("[ChatAgent] Action proposal suppressed: denial circuit breaker is tripped.")
            return None

        action_type = proposed.get("action_type")
        params = proposed.get("params", {})
        description = proposed.get("description", str(proposed))

        if action_type not in (
            "place_order",
            "close_position",
            "close_paper_trade",
            "pause_trading",
            "resume_trading",
            "modify_sl_tp",
            "modify_paper_sl_tp",
            "cancel_trigger",
            "save_market_intelligence",
            "db_mutation",
            "close_all_positions",
            "bulk_breakeven",
            "secure_positions",
            "cancel_order",
            "cancel_stale_pending_orders",
            "set_trailing_stop",
            "update_config",
            "update_user_preference",
            "execute_terminal_command",
            "desktop_gui_action",
            "partial_close_and_breakeven",
        ):
            logger.warning(f"Unknown proposed action type: {action_type}")
            return None

        if action_type == "db_mutation":
            tbl = params.get("table_name", "unknown")
            op = str(params.get("operation", "unknown")).upper()
            tid = params.get("target_id", "N/A")
            rsn = proposed.get("reason") or params.get("reason", "")
            description = (
                f"Modifikasi Database:\n"
                f"• Tabel: {tbl}\n"
                f"• Operasi: {op} (ID: {tid})\n"
                f"• Data: {json.dumps(params.get('data', {}))}\n"
                f"• Alasan: {rsn}"
            )
        elif action_type == "close_all_positions":
            flt = params.get("filter", "all")
            rsn = proposed.get("reason") or params.get("reason", "Permintaan penutupan posisi massal")
            description = f"Tutup Posisi Massal:\n• Filter: {flt}\n• Alasan: {rsn}"
        elif action_type in ("bulk_breakeven", "secure_positions"):
            sym = params.get("symbol", "SEMUA")
            op = params.get("only_profit", True)
            description = f"Amankan Posisi ke Breakeven:\n• Simbol: {sym}\n• Hanya Profit: {op}"
        elif action_type == "cancel_stale_pending_orders":
            max_age = params.get("max_age_hours", 24)
            description = f"Batalkan Stale Pending Order:\n• Usia Maksimal: {max_age} jam"
        elif action_type == "set_trailing_stop":
            target = params.get("symbol") or params.get("ticket") or "Semua posisi"
            tp = params.get("trailing_pips") or params.get("pips", "N/A")
            description = f"Set Trailing Stop:\n• Target: {target}\n• Trailing Pips: {tp}"
        elif action_type == "update_config":
            k = params.get("key") or params.get("parameter")
            v = params.get("value")
            description = f"Update Konfigurasi Sistem:\n• Parameter: {k}\n• Nilai Baru: {v}"
        elif action_type == "update_user_preference":
            c = params.get("category", "general")
            k = params.get("key", "preference")
            v = params.get("value")
            description = f"Update Preferensi User:\n• Kategori: {c}\n• Kunci: {k}\n• Nilai: {v}"
        elif action_type == "execute_terminal_command":
            cmd = params.get("command") or params.get("cmd") or "N/A"
            description = f"Eksekusi Shell Command:\n• Command: `{cmd}`"
        elif action_type == "desktop_gui_action":
            act = params.get("action", "unknown")
            description = f"Desktop GUI Interaction:\n• Aksi: {act}\n• Detail: {json.dumps(params)}"
        elif action_type == "partial_close_and_breakeven":
            tck = params.get("ticket")
            vol = params.get("volume") or params.get("lots")
            description = f"Partial Close & Geser Breakeven:\n• Tiket: #{tck}\n• Volume Ditutup: {vol} lot\n• SL Sisa: Geser ke BE (harga entri)"

        # HIGH-2: Tool Guardrail validation
        verdict = self.guardrail_controller.validate_tool_call(
            tool_name="propose_action",
            args={"action_type": action_type, "params": params},
            context={"trading_paused": self._proposals_paused, "is_admin": getattr(self, "is_admin", False)},
        )
        if not verdict.allowed:
            logger.warning(f"[ChatAgent] Action proposal blocked by guardrail ({verdict.guard_name}): {verdict.reason}")
            return None

        action_id = str(uuid.uuid4())[:8]
        return PendingAction(
            action_id=action_id,
            action_type=action_type,
            params=params,
            description=description,
        )
