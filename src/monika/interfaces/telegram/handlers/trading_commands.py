# ==============================================================================
# File: interfaces/telegram/handlers/trading_commands.py
# ==============================================================================

"""
Trading Operations Command Group for Telegram Bot.
Defines descriptors, permissions, and handler dispatch mapping for execution and risk controls.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.base import _TelegramBotMixinBase
from monika.interfaces.telegram.sanitizer import sanitize_telegram_html

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandDescriptor:
    name: str
    admin_only: bool
    description: str
    usage: str


TRADING_COMMAND_DESCRIPTORS: Dict[str, CommandDescriptor] = {
    "pause": CommandDescriptor("pause", True, "Jeda seluruh eksekusi trading otomatis", "/pause [durasi] [alasan]"),
    "resume": CommandDescriptor("resume", True, "Lanjutkan eksekusi trading setelah dijeda", "/resume"),
    "suspend": CommandDescriptor(
        "suspend", True, "Tangguhkan trading pada simbol tertentu", "/suspend <simbol> [alasan]"
    ),
    "unsuspend": CommandDescriptor("unsuspend", True, "Cabut penangguhan trading pada simbol", "/unsuspend <simbol>"),
    "kill": CommandDescriptor("kill", True, "Emergency liquidation: tutup semua posisi dan jeda sistem", "/kill"),
    "emergency": CommandDescriptor("emergency", True, "Alias untuk kill switch darurat", "/emergency"),
    "close": CommandDescriptor("close", True, "Tutup posisi trading tertentu berdasarkan tiket", "/close <ticket>"),
    "closeall": CommandDescriptor("closeall", True, "Tutup semua posisi terbuka dengan konfirmasi", "/closeall"),
    "override": CommandDescriptor("override", True, "Override status intervensi manual", "/override <alasan>"),
    "run": CommandDescriptor("run", True, "Jalankan siklus analisis dan trading manual secara paksa", "/run"),
    "orders": CommandDescriptor("orders", False, "Daftar order aktif dan pending", "/orders"),
    "trailing": CommandDescriptor("trailing", False, "Status dan pengaturan trailing stop", "/trailing [simbol]"),
    "reconcile": CommandDescriptor("reconcile", True, "Rekonsiliasi posisi antara DB dan broker MT5", "/reconcile"),
}


async def execute_trading_command(
    command: str,
    args: list[str],
    session: Any,
    actor: str = "telegram_operator",
    broker_adapter: Any = None,
) -> Dict[str, Any]:
    """Execute trading operational command through TradingService and PortfolioService."""
    from monika.application.services.portfolio_service import PortfolioService
    from monika.application.services.trading_service import TradingService

    cmd = command.lower().strip()
    if cmd in ("kill", "emergency"):
        reason = " ".join(args) if args else "Emergency stop via Telegram"
        return await TradingService.emergency_kill(session, reason=reason, actor=actor)

    elif cmd == "close":
        if not args:
            return {"success": False, "message": "Usage: /close <ticket>"}
        try:
            ticket = int(args[0])
            ok = await TradingService.close_position(
                session=session,
                ticket=ticket,
                reason="Telegram operator close",
                actor=actor,
                broker_adapter=broker_adapter,
            )
            return {"success": ok, "ticket": ticket}
        except ValueError:
            return {"success": False, "message": f"Invalid ticket: {args[0]}"}

    elif cmd == "positions":
        positions = await PortfolioService.get_open_positions(session)
        return {"success": True, "count": len(positions), "positions": positions}

    return {"success": False, "message": f"Unknown trading command: {command}"}


class TelegramTradingCommandsMixin(_TelegramBotMixinBase):
    """Mixin providing execution and trading operation command handlers for TelegramBot."""

    async def _cmd_interrupt(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else user_id
        thread_id = getattr(update.message, "message_thread_id", None)
        agent = None
        if isinstance(thread_id, int) and hasattr(self, "topic_manager") and self.topic_manager:
            topic_session = await self.topic_manager.get_session_for_topic(chat_id, thread_id)
            if topic_session:
                agent = self._chat_agents.get(topic_session)
        if not agent:
            agent = self._chat_agents.get(user_id)

        if agent:
            redirect_msg = " ".join(ctx.args) if ctx.args else "Turn interrupted by user"
            success = agent.interrupt(redirect_msg)
            if success:
                await update.message.reply_text(f"[BERHENTI] Analysis interrupted. Note: {redirect_msg}")
            else:
                await update.message.reply_text("[INFORMASI] No active task currently executing for your session.")
        else:
            await update.message.reply_text("[INFORMASI] No active chat session found.")

    async def _cmd_resume_proposals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else user_id
        thread_id = getattr(update.message, "message_thread_id", None)
        agent = None
        if isinstance(thread_id, int) and hasattr(self, "topic_manager") and self.topic_manager:
            topic_session = await self.topic_manager.get_session_for_topic(chat_id, thread_id)
            if topic_session:
                agent = self._chat_agents.get(topic_session)
        if not agent:
            agent = self._chat_agents.get(user_id)

        if agent:
            res = agent.resume_proposals()
            await update.message.reply_text(f"[BERHASIL] {res}")
        else:
            await update.message.reply_text("[INFORMASI] No active chat session found.")

    async def _cmd_approvals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        from monika.domain.risk.approval_hub import ApprovalHub
        from monika.interfaces.telegram.message_formatter import format_approvals_slip

        try:
            hub = ApprovalHub.get_instance()
            open_reqs = hub.get_open_requests()
            raw_text = format_approvals_slip(open_reqs)
            safe_text = sanitize_telegram_html(raw_text)

            kb = []
            for req in open_reqs:
                token = getattr(req, "token", getattr(req, "request_id", ""))
                short_id = token[:6]
                kb.append(
                    [
                        InlineKeyboardButton(f"✅ Setujui #{short_id}", callback_data=f"appr_yes:{token}"),
                        InlineKeyboardButton(f"❌ Tolak #{short_id}", callback_data=f"appr_no:{token}"),
                    ]
                )

            markup = InlineKeyboardMarkup(kb) if kb else None
            await update.message.reply_text(safe_text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            await update.message.reply_text(
                f"[GAGAL] Error memuat approvals: {html.escape(str(e))}", parse_mode=ParseMode.HTML
            )

    async def _cmd_trailing(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        if not ctx.args:
            text = await self._build_trailing_text()
            await update.message.reply_text(sanitize_telegram_html(text), parse_mode=ParseMode.HTML)
            return

        # Handle per-ticket override: /trailing <ticket> <trail_mult> [be_mult]
        # or /trailing <ticket> disable / reset
        import json

        from sqlalchemy import or_, select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import Position

        ticket_str = ctx.args[0].strip().replace("#", "")
        if not ticket_str.isdigit():
            await update.message.reply_text(
                "Penggunaan:\n"
                "- <code>/trailing</code> : Lihat status trailing semua posisi\n"
                "- <code>/trailing &lt;ticket&gt; &lt;trail_mult&gt; [be_mult]</code> : Atur trailing kustom\n"
                "- <code>/trailing &lt;ticket&gt; disable</code> : Matikan trailing tiket ini\n"
                "- <code>/trailing &lt;ticket&gt; reset</code> : Kembalikan ke default global",
                parse_mode=ParseMode.HTML,
            )
            return

        ticket_num = int(ticket_str)
        arg_action = ctx.args[1].lower().strip() if len(ctx.args) > 1 else ""

        async with get_session() as session:
            stmt = (
                select(Position)
                .where(or_(Position.mt5_ticket == ticket_num, Position.id == ticket_num), Position.closed_at.is_(None))
                .limit(1)
            )
            pos = (await session.execute(stmt)).scalar_one_or_none()
            if not pos:
                await update.message.reply_text(
                    f"[PERINGATAN] Posisi aktif dengan ticket #{ticket_num} tidak ditemukan."
                )
                return

            if arg_action in ("reset", "default", "clear"):
                pos.trailing_override_json = None
                await session.commit()
                await update.message.reply_text(
                    f"[BERHASIL] Trailing override untuk tiket #{ticket_num} ({pos.symbol}) di-reset ke default global."
                )
                return

            if arg_action in ("off", "disable", "disabled", "stop"):
                pos.trailing_override_json = json.dumps({"disabled": True})
                await session.commit()
                await update.message.reply_text(
                    f"[BERHENTI] Trailing stop untuk tiket #{ticket_num} ({pos.symbol}) dinonaktifkan."
                )
                return

            try:
                trail_val = float(arg_action)
                be_val = float(ctx.args[2]) if len(ctx.args) > 2 else 1.0
                override_data = {
                    "trail_atr_multiple": trail_val,
                    "breakeven_atr_multiple": be_val,
                    "disabled": False,
                }
                pos.trailing_override_json = json.dumps(override_data)
                await session.commit()
                await update.message.reply_text(
                    f"[BERHASIL] Trailing stop override tiket #{ticket_num} ({pos.symbol}) aktif:\n"
                    f"- Trail ATR Multiple: `{trail_val}x`\n"
                    f"- Breakeven ATR Multiple: `{be_val}x`",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except ValueError:
                await update.message.reply_text(
                    f"[PERINGATAN] Nilai multiple ATR '{arg_action}' tidak valid. Masukkan angka (misal: 1.5).",
                    parse_mode=ParseMode.MARKDOWN,
                )

    async def _cmd_reconcile(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_reconcile_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_orders(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Display pending limit/stop orders in MT5 (/orders)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            from monika.infrastructure.brokers.mt5_client import _get_orders

            orders = _get_orders()
        except Exception:
            orders = []

        if not orders:
            await update.message.reply_text(
                "[ INFO ] Tidak ada pending order yang aktif di broker MT5.", parse_mode=ParseMode.HTML
            )
            return

        lines = ["📋 <b>DAFTAR PENDING ORDERS MT5</b>\n"]
        kb = []
        for o in orders:
            ticket = o.get("ticket")
            sym = o.get("symbol", "")
            direction = str(o.get("direction", "")).upper()
            vol = o.get("volume", 0.0)
            price_open = o.get("price_open", 0.0)
            sl = o.get("sl") or "-"
            tp = o.get("tp") or "-"
            lines.append(
                f"• <b>#{ticket}</b> | <code>{sym}</code> {direction} {vol} lot\n"
                f"  Open: <code>{price_open}</code> | SL: <code>{sl}</code> | TP: <code>{tp}</code>"
            )
            if ticket:
                kb.append([InlineKeyboardButton(f"❌ Batalkan #{ticket} ({sym})", callback_data=f"cancel:{ticket}")])

        markup = InlineKeyboardMarkup(kb) if kb else None
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)

    async def _cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)
        clean_args = [a for a in ctx.args if a not in ("-y", "--force")] if ctx.args else []
        duration_hours = None
        duration_desc = ""
        reason = "Paused via Telegram"

        if clean_args:
            full_str = " ".join(clean_args).lower().strip()
            import re

            m = re.match(
                r"^(\d+(?:\.\d+)?)\s*(m|min|mins|menit|minutes?|h|hr|hrs|jam|hours?|d|hari|days?)(?:\s+(.*))?$",
                full_str,
            )
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                rem_reason = (m.group(3) or "").strip()
                if unit.startswith("m"):
                    duration_hours = val / 60.0
                    duration_desc = f"{val:.0f} menit"
                elif unit.startswith("d") or unit == "hari":
                    duration_hours = val * 24.0
                    duration_desc = f"{val:.0f} hari"
                else:
                    duration_hours = val
                    duration_desc = f"{val:g} jam"
                reason = rem_reason if rem_reason else f"Jeda otomatis {duration_desc}"
            else:
                reason = " ".join(clean_args)

        if not ctx.args or ("-y" not in ctx.args and "--force" not in ctx.args):
            import secrets
            import time

            nonce = secrets.token_hex(4)
            if not hasattr(self, "_active_nonces"):
                self._active_nonces = {}
            self._active_nonces[nonce] = {
                "action": "pause",
                "reason": reason,
                "duration_hours": duration_hours,
                "duration_desc": duration_desc,
                "expires": time.time() + 120.0,
            }

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("[ KONFIRMASI JEDA ]", callback_data=f"pause:confirm:{nonce}"),
                        InlineKeyboardButton("[ BATAL ]", callback_data="cancel"),
                    ]
                ]
            )
            dur_line = f"Durasi: {duration_desc} (auto-unpause)\n" if duration_desc else ""
            await update.message.reply_text(
                f"[ PERINGATAN: KONFIRMASI JEDA TRADING ]\n\n"
                f"Alasan: {reason}\n"
                f"{dur_line}"
                f"Apakah Anda yakin ingin menjeda seluruh eksekusi trading?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            return

        from monika.domain.risk.risk_gate import RiskGate
        from monika.infrastructure.database.db import get_session

        gate = RiskGate(self.settings)
        async with get_session() as session:
            await gate.pause_trading(session, reason, duration_hours=duration_hours)
        dur_msg = f"\nDurasi: {duration_desc} (auto-unpause aktif)" if duration_desc else ""
        await update.message.reply_text(
            f"[ PAUSED ] Trading dijeda.\nAlasan: {reason}{dur_msg}", parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)
        from monika.core.analytics.cost_tracker import CostTracker
        from monika.domain.risk.risk_gate import RiskGate
        from monika.infrastructure.database.db import get_session

        async with get_session() as session:
            if (
                hasattr(self, "execution_service")
                and self.execution_service
                and hasattr(self.execution_service, "resume_trading")
            ):
                await self.execution_service.resume_trading(session, requested_by="telegram_admin")
            else:
                gate = RiskGate(self.settings)
                await gate.resume_trading(session)
            await CostTracker.clear_budget_pause(session)
        await update.message.reply_text(
            "[ RESUMED ] Trading & AI Budget dilanjutkan (All pause & kill flags cleared).",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_suspend(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        from monika.core.analytics.paper_tracker import PaperTracker
        from monika.infrastructure.database.db import get_session

        tracker = PaperTracker(self.settings)

        if not ctx.args:
            async with get_session() as session:
                suspended = await tracker.get_suspended_symbols(session)
            if suspended:
                items_str = ", ".join(f"`{s}`" for s in suspended)
                msg = f"[TERKUNCI] *Simbol tersuspensi saat ini ({len(suspended)}):*\n{items_str}\n\n"
            else:
                msg = "[INFORMASI] Tidak ada simbol yang tersuspensi saat ini.\n\n"
            msg += (
                "Penggunaan:\n"
                "- `/suspend <symbol> <durasi> [alasan]`\n"
                "Contoh: `/suspend EURUSD 24h market spike`\n"
                "Contoh: `/suspend XAUUSD 3d NFP week`\n"
                "- `/unsuspend <symbol>` untuk membuka suspensi."
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        target_sym = ctx.args[0].strip().upper().replace("/", "")
        dur_str = ctx.args[1].lower().strip() if len(ctx.args) > 1 else "24h"
        import re

        dur_hours = 24.0
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)$", dur_str)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if unit.startswith("m"):
                dur_hours = val / 60.0
            elif unit.startswith("d"):
                dur_hours = val * 24.0
            else:
                dur_hours = val
            reason_tokens = ctx.args[2:]
        else:
            reason_tokens = ctx.args[1:]

        reason = " ".join(reason_tokens) if reason_tokens else "Manual suspension via Telegram"

        async with get_session() as session:
            res = await tracker.suspend_symbol(
                session=session,
                symbol=target_sym,
                duration_hours=dur_hours,
                reason=reason,
            )

        await update.message.reply_text(
            f"[TERKUNCI] *Simbol {target_sym} berhasil disuspend!*\n"
            f"- Durasi: `{dur_hours:g} jam`\n"
            f"- Berakhir pada: `{res.get('until', '-')}`\n"
            f"- Alasan: {reason}",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_unsuspend(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text(
                "Penggunaan: `/unsuspend <symbol>` atau `/unsuspend all`", parse_mode=ParseMode.MARKDOWN
            )
            return

        target = ctx.args[0].strip().upper()
        from monika.core.analytics.paper_tracker import PaperTracker
        from monika.infrastructure.database.db import get_session

        tracker = PaperTracker(self.settings)
        async with get_session() as session:
            if target == "ALL":
                if not ctx.args or ("-y" not in ctx.args and "--force" not in ctx.args):
                    import secrets
                    import time

                    nonce = secrets.token_hex(4)
                    if not hasattr(self, "_active_nonces"):
                        self._active_nonces = {}
                    self._active_nonces[nonce] = {"action": "unsuspend_all", "expires": time.time() + 120.0}

                    keyboard = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "[ CONFIRM UNSUSPEND ALL ]", callback_data=f"unsuspend_all:confirm:{nonce}"
                                ),
                                InlineKeyboardButton("[ CANCEL ]", callback_data="cancel"),
                            ]
                        ]
                    )
                    await update.message.reply_text(
                        "[PERINGATAN] *CONFIRMATION REQUIRED: UNSUSPEND ALL*\n\n"
                        "Are you sure you want to lift trading suspension on all instruments?",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=keyboard,
                    )
                    return

                cleared = await tracker.unsuspend_all(session)
                if cleared:
                    await update.message.reply_text(
                        f"[ OK ] Berhasil membuka blokir semua simbol: `{', '.join(cleared)}`",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                else:
                    await update.message.reply_text(
                        "[ INFO ] Tidak ada simbol yang sedang tersuspensi.", parse_mode=ParseMode.MARKDOWN
                    )
            else:
                ok = await tracker.unsuspend_symbol(session, target)
                if ok:
                    await update.message.reply_text(
                        f"[ OK ] Berhasil membuka blokir simbol *{target}*.", parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await update.message.reply_text(
                        f"[ INFO ] Simbol *{target}* tidak ditemukan dalam daftar suspensi.",
                        parse_mode=ParseMode.MARKDOWN,
                    )

    async def _cmd_kill(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        import secrets
        import time

        nonce = secrets.token_hex(4)
        if not hasattr(self, "_active_nonces"):
            self._active_nonces = {}
        self._active_nonces[nonce] = {"action": "killswitch", "expires": time.time() + 120.0}

        # Two-step confirm for kill switch with single-use nonce
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("[ KONFIRMASI TUTUP SEMUA ]", callback_data=f"killswitch:confirm:{nonce}"),
                    InlineKeyboardButton("[ BATAL ]", callback_data="cancel"),
                ]
            ]
        )
        await update.message.reply_text(
            "[ PERINGATAN: EMERGENCY KILL SWITCH ]\n\n"
            "Tindakan ini akan menutup SEMUA posisi terbuka dan menghentikan trading baru.\n\n"
            "Konfirmasi eksekusi?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    async def _cmd_emergency(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_non_admin(update)
        # Langsung execute tanpa konfirmasi
        await update.message.reply_text("[DARURAT] EMERGENCY CLOSE INITIATED - NO CONFIRMATION NEEDED")
        if self.execution_service:
            result = await self.execution_service.kill_switch("EMERGENCY TELEGRAM COMMAND - INSTANT")
            await update.message.reply_text(
                f"[VOLATILITAS] Emergency close done: {result['closed']}/{result['total']} positions closed"
            )
        else:
            await update.message.reply_text("[PERINGATAN] ExecutionService tidak terhubung.")

    async def _cmd_close(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text(
                "Usage: /close <ticket> [volume|percentage%]\nContoh: `/close 12345` atau `/close 12345 50%` atau `/close 12345 0.05`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        try:
            ticket = int(ctx.args[0].replace("#", ""))
        except ValueError:
            await update.message.reply_text("[GAGAL] Ticket harus berupa angka.")
            return

        volume = None
        if len(ctx.args) > 1:
            vol_arg = ctx.args[1].strip()
            if vol_arg.endswith("%"):
                try:
                    pct = float(vol_arg.rstrip("%")) / 100.0
                    from sqlalchemy import or_, select

                    from monika.infrastructure.database.db import get_session
                    from monika.infrastructure.database.models import Position

                    async with get_session() as session:
                        pos = (
                            await session.execute(
                                select(Position)
                                .where(or_(Position.mt5_ticket == ticket, Position.id == ticket))
                                .limit(1)
                            )
                        ).scalar_one_or_none()
                        if pos and pos.volume:
                            volume = round(float(pos.volume) * pct, 2)
                except Exception:
                    volume = None
            else:
                try:
                    volume = float(vol_arg)
                except ValueError:
                    volume = None

        from monika.interfaces.telegram.command_router import CommandRouter

        keyboard = CommandRouter.build_close_keyboard(ticket, volume=volume)
        vol_desc = f" ({volume} lot)" if volume is not None else ""
        await update.message.reply_text(
            f"[PERINGATAN] Konfirmasi tutup posisi *#{ticket}*{vol_desc}?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    async def _cmd_cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Membatalkan pending order MT5 (/cancel <ticket>)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            if self.execution_service and hasattr(self.execution_service, "mt5"):
                try:
                    orders = await self.execution_service.mt5.get_pending_orders()
                    if orders:
                        lines = ["[DATA] *Daftar Pending Order:*"]
                        for o in orders:
                            lines.append(
                                f"• Ticket `#{o.get('ticket')}`: *{o.get('symbol')}* {o.get('type_str', '').upper()} {o.get('volume_initial', o.get('volume'))} lot @ `{o.get('price_open')}`"
                            )
                        lines.append("\nKetik `/cancel <ticket>` untuk membatalkan.")
                        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
                        return
                    else:
                        await update.message.reply_text("[INFORMASI] Tidak ada pending order yang aktif saat ini.")
                        return
                except Exception as e:
                    logger.warning(f"Failed to fetch pending orders: {e}")
            await update.message.reply_text("Penggunaan: `/cancel <ticket>`", parse_mode=ParseMode.MARKDOWN)
            return

        ticket_str = ctx.args[0].strip().replace("#", "")
        if not ticket_str.isdigit():
            await update.message.reply_text("[GAGAL] Ticket harus berupa angka.")
            return

        ticket = int(ticket_str)
        if not self.execution_service or not hasattr(self.execution_service, "mt5"):
            await update.message.reply_text("[PERINGATAN] ExecutionService MT5 tidak terhubung.")
            return

        res = await self.execution_service.mt5.cancel_order(ticket)
        if res.get("success"):
            await update.message.reply_text(
                f"[BERHASIL] Pending order `#{ticket}` berhasil dibatalkan.", parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"[GAGAL] Gagal membatalkan order `#{ticket}`: {res.get('error', 'Unknown error')}",
                parse_mode=ParseMode.MARKDOWN,
            )

    async def _cmd_closeall(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Tutup semua posisi aktif (Admin only)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not self.execution_service:
            await update.message.reply_text("[PERINGATAN] ExecutionService tidak terhubung.")
            return

        if not ctx.args or ("-y" not in ctx.args and "--force" not in ctx.args):
            import secrets
            import time

            nonce = secrets.token_hex(4)
            if not hasattr(self, "_active_nonces"):
                self._active_nonces = {}
            self._active_nonces[nonce] = {"action": "closeall", "expires": time.time() + 120.0}

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "[ [DARURAT] CONFIRM CLOSE ALL ]", callback_data=f"closeall:confirm:{nonce}"
                        ),
                        InlineKeyboardButton("[ CANCEL ]", callback_data="cancel"),
                    ]
                ]
            )
            await update.message.reply_text(
                "[DARURAT] *CONFIRMATION REQUIRED: CLOSE ALL POSITIONS*\n\n"
                "Are you sure you want to close ALL active open positions immediately?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            return

        await update.message.reply_text("[DARURAT] Memproses penutupan seluruh posisi terbuka...")
        try:
            if hasattr(self.execution_service, "close_all_positions"):
                result = await self.execution_service.close_all_positions(comment="TG:CloseAll")
            elif hasattr(self.execution_service, "kill_switch"):
                result = await self.execution_service.kill_switch("Telegram /closeall command")
            else:
                result = {"status": "error", "message": "Method close_all_positions not available"}

            closed = result.get("closed", 0)
            total = result.get("total", 0)
            await update.message.reply_text(
                f"[BERHASIL] *Close All Selesai*: {closed}/{total} posisi berhasil ditutup.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await update.message.reply_text(f"[GAGAL] Gagal menutup semua posisi: {e}")

    async def _cmd_override(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Ubah parameter risiko secara dinamis (Admin only)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args or len(ctx.args) < 2:
            help_text = (
                "[KONFIGURASI] *Penggunaan /override:*\n"
                "• `/override max_risk <0.1-5.0>` — Risk per trade (%)\n"
                "• `/override max_daily_dd <0.5-20.0>` — Max daily drawdown (%)\n"
                "• `/override max_positions <1-20>` — Max concurrent positions\n"
                "• `/override auto_execute <true|false>` — Auto execution mode\n"
                "• `/override reset` — Reset semua override"
            )
            await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
            return

        param = ctx.args[0].lower().strip()
        val_str = ctx.args[1].lower().strip()

        field_map = {
            "max_risk": "risk_percent_per_trade",
            "risk": "risk_percent_per_trade",
            "max_daily_dd": "max_daily_drawdown_percent",
            "daily_dd": "max_daily_drawdown_percent",
            "max_positions": "max_concurrent_positions",
            "positions": "max_concurrent_positions",
            "auto_execute": "auto_execute",
        }

        updated_fields: dict[str, Any] = {}
        if param == "reset":
            updated_fields = {}
        elif param in field_map:
            key = field_map[param]
            try:
                if key == "auto_execute":
                    updated_fields[key] = val_str in ("true", "1", "yes")
                elif key == "max_concurrent_positions":
                    updated_fields[key] = int(val_str)
                else:
                    updated_fields[key] = float(val_str)
            except ValueError:
                await update.message.reply_text(f"[GAGAL] Nilai tidak valid untuk `{param}`: {val_str}")
                return
        else:
            await update.message.reply_text(
                f"[GAGAL] Parameter `{param}` tidak dikenali. Ketik `/override` untuk opsi."
            )
            return

        if "-y" not in ctx.args and "--force" not in ctx.args:
            import secrets
            import time

            nonce = secrets.token_hex(4)
            if not hasattr(self, "_active_nonces"):
                self._active_nonces = {}
            self._active_nonces[nonce] = {
                "action": "override",
                "param": param,
                "val_str": val_str,
                "updated_fields": updated_fields,
                "expires": time.time() + 120.0,
            }

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("[ CONFIRM OVERRIDE ]", callback_data=f"override:confirm:{nonce}"),
                        InlineKeyboardButton("[ CANCEL ]", callback_data="cancel"),
                    ]
                ]
            )
            await update.message.reply_text(
                f"[KONFIGURASI] *CONFIRMATION REQUIRED: RISK OVERRIDE*\n\n"
                f"Parameter: `{param}`\n"
                f"New Value: `{val_str}`\n"
                f"Fields: `{updated_fields if param != 'reset' else 'RESET ALL'}`\n\n"
                f"Apply this dynamic risk parameter change?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            return

        import json

        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import ActivityLog, SystemConfig

        async with get_session() as session:
            cfg_row = (
                await session.execute(select(SystemConfig).where(SystemConfig.key == "risk_override"))
            ).scalar_one_or_none()

            current_cfg = {}
            if cfg_row and cfg_row.value:
                try:
                    current_cfg = json.loads(cfg_row.value)
                except Exception:
                    pass

            if param == "reset":
                current_cfg.clear()
            else:
                current_cfg.update(updated_fields)

            if cfg_row:
                cfg_row.value = json.dumps(current_cfg)
            else:
                session.add(SystemConfig(key="risk_override", value=json.dumps(current_cfg)))

            session.add(
                ActivityLog(
                    category="risk",
                    description=f"Risk override via Telegram: {updated_fields if param != 'reset' else 'RESET'}",
                    actor="telegram_admin",
                )
            )
            await session.commit()

        if hasattr(self, "settings") and isinstance(self.settings, dict):
            trading_risk = self.settings.setdefault("trading", {}).setdefault("risk", {})
            trading_risk.update(current_cfg)

        try:
            from monika.interfaces.dashboard.routes.common import broadcast_live_event

            await broadcast_live_event(
                "risk_override_updated",
                {
                    "updated_fields": current_cfg,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"[BERHASIL] *Risk Override Diterapkan:*\n`{json.dumps(current_cfg, indent=2)}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_run(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        await update.message.reply_text("[SINKRONISASI] Menjalankan siklus analisis manual...")
        if self.cycle_scheduler:
            asyncio.create_task(self._run_cycle_and_notify(update))
        else:
            await update.message.reply_text("[PERINGATAN] Scheduler tidak terhubung.")

    async def _run_cycle_and_notify(self, update: Update) -> None:
        if not self.cycle_scheduler or not update.message:
            return
        try:
            summary = await self.cycle_scheduler.run_once(forced=True)
            pa = summary.get("per_asset", {})
            lines = [f"[BERHASIL] *Siklus analisis selesai*"]
            for sym, r in pa.items():
                decision = (r.get("decision") or "N/A").upper()
                conf = r.get("confidence") or 0
                lines.append(f"  {sym}: `{decision}` ({conf:.0%})")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"[GAGAL] Siklus gagal: {e}")

    async def _cmd_approve(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text("Usage: /approve <analysis_id>")
            return

        try:
            analysis_id = int(ctx.args[0])
        except ValueError:
            await update.message.reply_text("[GAGAL] analysis_id harus berupa angka.")
            return

        if not self.execution_service:
            await update.message.reply_text("[PERINGATAN] ExecutionService tidak terhubung.")
            return

        await update.message.reply_text(f"[MEMPROSES] Mengeksekusi analisis #{analysis_id}...")
        try:
            result = await self.execution_service.execute_by_analysis_id(analysis_id)
            try:
                from monika.domain.risk.approval_hub import ApprovalHub

                user_id = update.effective_user.id if update.effective_user else "unknown"
                await ApprovalHub.get_instance().approve(str(analysis_id), operator=f"telegram:{user_id}")
            except Exception:
                pass
            await update.message.reply_text(
                f"[BERHASIL] {result.summary()}" if hasattr(result, "summary") else str(result)
            )
        except Exception as e:
            await update.message.reply_text(f"[GAGAL] Gagal: {e}")

    async def _cmd_reject(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text("Usage: /reject <analysis_id>")
            return

        analysis_id_str = ctx.args[0]

        try:
            from monika.domain.risk.approval_hub import ApprovalHub

            user_id = update.effective_user.id if update.effective_user else "unknown"
            await ApprovalHub.get_instance().reject(
                str(analysis_id_str), operator=f"telegram:{user_id}", reason="Rejected via Telegram by admin"
            )
        except Exception:
            pass

        from monika.infrastructure.database.db import get_session

        async with get_session() as session:
            from sqlalchemy import select
            from sqlalchemy import update as sql_update

            from monika.infrastructure.database.models import ActivityLog, PaperTradeRecord

            session.add(
                ActivityLog(
                    category="trading",
                    description=f"Trade proposal #{analysis_id_str} REJECTED by admin via Telegram",
                    actor="telegram_admin",
                )
            )

            try:
                analysis_id = int(analysis_id_str)

                from monika.infrastructure.database.models import AssetAnalysis

                await session.execute(
                    sql_update(AssetAnalysis)
                    .where(AssetAnalysis.id == analysis_id)
                    .values(execution_status="rejected", execution_notes="Rejected via Telegram by admin")
                )

                await session.execute(
                    sql_update(PaperTradeRecord)
                    .where(PaperTradeRecord.analysis_id == analysis_id)
                    .where(PaperTradeRecord.status == "open")
                    .values(
                        status="closed",
                        closed_at=datetime.now(timezone.utc),
                        exit_reason="rejected_by_admin",
                        pnl_pct=0.0,
                    )
                )
            except (ValueError, Exception) as e:
                logger.debug(f"Paper trade cleanup on reject (non-fatal): {e}")

            await session.commit()

        await update.message.reply_text(f"[GAGAL] Analisis #{analysis_id_str} ditolak dan tidak akan dieksekusi.")

    async def _cmd_steer(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Mid-stream in-flight steer directive synchronized across Telegram, WS, and TUI."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args or len(ctx.args) < 2:
            await update.message.reply_text(
                "Usage: `/steer <symbol> <instruction>`\nContoh: `/steer EURUSD prioritize bearish sweep reclaim`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        symbol = ctx.args[0].upper().strip()
        instruction = " ".join(ctx.args[1:]).strip()

        from monika.domain.risk.approval_hub import ApprovalHub

        user_id = update.effective_user.id if update.effective_user else "unknown"
        operator_tag = f"telegram:{user_id}"
        await ApprovalHub.get_instance().steer(symbol, instruction, operator=operator_tag)

        await update.message.reply_text(
            f"[TARGET] *Steer Synchronized Across All Surfaces*\n\n"
            f"• *Symbol:* `{symbol}`\n"
            f"• *Instruction:* {instruction}\n"
            f"• *Surfaces:* Telegram, Dashboard CRT, TUI Terminal\n"
            f"• *Status:* Injected into active trading cycle",
            parse_mode=ParseMode.MARKDOWN,
        )


__all__ = [
    "CommandDescriptor",
    "TRADING_COMMAND_DESCRIPTORS",
    "execute_trading_command",
    "TelegramTradingCommandsMixin",
]
