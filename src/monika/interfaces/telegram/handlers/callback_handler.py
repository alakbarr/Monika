# ==============================================================================
# File: interfaces/telegram/handlers/callback_handler.py
# ==============================================================================

"""
Inline keyboard callback query handler mixin for Telegram bot.
Dispatches action callbacks for approvals, trading commands, plugin toggles, and UI interactions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.base import _TelegramBotMixinBase

logger = logging.getLogger(__name__)


class TelegramCallbackHandlerMixin(_TelegramBotMixinBase):
    """Mixin providing inline keyboard callback query dispatch for TelegramBot."""

    async def _handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()  # Acknowledge to remove loading spinner

        if not self._is_authorized(update):
            await query.edit_message_text("[AKSES DITOLAK] Unauthorized.")
            return

        user_id = update.effective_user.id if update.effective_user else 0
        data = query.data or ""

        if data == "cancel":
            await query.edit_message_text("[GAGAL] Dibatalkan.")
            return

        if data.startswith("cmd:"):
            cmd_target = data.split(":", 1)[1]
            handler_method = getattr(self, f"_cmd_{cmd_target}", None)
            if handler_method:
                if update.message is None and isinstance(query.message, Message):
                    update.message = query.message
                await handler_method(update, ctx)
            else:
                await query.edit_message_text(f"Command `/{cmd_target}` is not available via shortcut.")
            return

        if data.startswith("closeall:confirm:"):
            nonce = data.split(":", 2)[2]
            stored = getattr(self, "_active_nonces", {}).pop(nonce, None)

            if not stored or time.time() > stored.get("expires", 0):
                await query.edit_message_text("[PERINGATAN] Confirmation expired or invalid.")
                return
            await query.edit_message_text("[DARURAT] Memproses likuidasi seluruh posisi terbuka...")
            if self.execution_service:
                if hasattr(self.execution_service, "close_all_positions"):
                    result = await self.execution_service.close_all_positions(comment="TG:CloseAll")
                elif hasattr(self.execution_service, "kill_switch"):
                    result = await self.execution_service.kill_switch("Telegram /closeall command")
                else:
                    result = {"status": "error", "message": "Method close_all_positions not available"}
                closed = result.get("closed", 0)
                total = result.get("total", 0)
                await query.edit_message_text(f"[BERHASIL] Close All Selesai: {closed}/{total} posisi ditutup.")
            else:
                await query.edit_message_text("[PERINGATAN] ExecutionService tidak terhubung.")
            return

        if data.startswith("unsuspend_all:confirm:"):
            nonce = data.split(":", 2)[2]
            stored = getattr(self, "_active_nonces", {}).pop(nonce, None)

            if not stored or time.time() > stored.get("expires", 0):
                await query.edit_message_text("[PERINGATAN] Confirmation expired or invalid.")
                return
            from monika.core.analytics.paper_tracker import PaperTracker
            from monika.infrastructure.database.db import get_session

            tracker = PaperTracker(self.settings)
            async with get_session() as session:
                cleared = await tracker.unsuspend_all(session)
                if cleared:
                    await query.edit_message_text(f"[ OK ] Berhasil membuka blokir semua simbol: {', '.join(cleared)}")
                else:
                    await query.edit_message_text("[ INFO ] Tidak ada simbol yang sedang tersuspensi.")
            return

        if data.startswith("override:confirm:"):
            nonce = data.split(":", 2)[2]
            stored = getattr(self, "_active_nonces", {}).pop(nonce, None)
            if not stored or time.time() > stored.get("expires", 0):
                await query.edit_message_text("[PERINGATAN] Confirmation expired or invalid.")
                return
            updated_fields = stored.get("updated_fields", {})
            param = stored.get("param", "")

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
                        description=f"Risk override confirmed via Telegram: {updated_fields if param != 'reset' else 'RESET'}",
                        actor="telegram_admin",
                    )
                )
                await session.commit()
            await query.edit_message_text(
                f"[BERHASIL] Risk parameter override applied: {updated_fields if param != 'reset' else 'RESET ALL'}"
            )
            return

        if data.startswith("plg:"):
            from monika.application.plugins.engine.installer import (
                get_community_catalog,
                list_all_plugins_status,
                run_pip_install,
                toggle_plugin_state,
            )

            if data == "plg:ref":
                plugins = list_all_plugins_status()
                text = self._build_plugins_text(plugins)
                markup = self._build_plugins_keyboard(plugins)
                try:
                    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                except Exception:
                    pass
                return

            if data == "plg:cat":
                catalog = get_community_catalog()
                lines = ["[MODUL] <b>KATALOG MARKETPLACE PLUG-IN MONIKA</b>\n"]
                kb = []
                for idx, item in enumerate(catalog):
                    lines.append(
                        f"• <b>{item['name']}</b> (<code>{item['package']}</code>)\n  <i>{item['description']}</i>\n"
                    )
                    kb.append(
                        [InlineKeyboardButton(f"[TERIMA] Install {item['name'][:20]}", callback_data=f"plg:inst:{idx}")]
                    )
                kb.append([InlineKeyboardButton("[PLUGIN] Plugins Terpasang", callback_data="plg:ref")])
                try:
                    await query.edit_message_text(
                        "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
                    )
                except Exception:
                    pass
                return

            if data.startswith("plg:t:"):
                if not self._is_admin(update):
                    await query.answer(
                        "[AKSES DITOLAK] Hanya Admin yang berhak mengubah status plugin.", show_alert=True
                    )
                    return
                plugin_id = data.split(":", 2)[2]
                plugins = {p["id"]: p for p in list_all_plugins_status()}
                if plugin_id in plugins:
                    p = plugins[plugin_id]
                    if not p.get("can_toggle", True):
                        await query.answer(
                            "[PERINGATAN] Komponen inti (core) tidak dapat dinonaktifkan.", show_alert=True
                        )
                        return
                    new_state = not p["enabled"]
                    ok, msg = toggle_plugin_state(plugin_id, p["category"], new_state)
                    await query.answer(
                        f"{'[AKTIF] Diaktifkan' if new_state else '[NONAKTIF] Dinonaktifkan'}: {plugin_id}"
                    )
                    new_plugins = list_all_plugins_status()
                    new_text = self._build_plugins_text(new_plugins)
                    new_markup = self._build_plugins_keyboard(new_plugins)
                    try:
                        await query.edit_message_text(new_text, parse_mode=ParseMode.HTML, reply_markup=new_markup)
                    except Exception:
                        pass
                else:
                    await query.answer(f"Plugin {plugin_id} tidak ditemukan.")
                return

            if data.startswith("plg:inst:"):
                if not self._is_admin(update):
                    await query.answer("[AKSES DITOLAK] Hanya Admin yang berhak menginstall plugin.", show_alert=True)
                    return
                pkg_arg = data.split(":", 2)[2]
                catalog = get_community_catalog()
                if pkg_arg.isdigit() and int(pkg_arg) < len(catalog):
                    pkg = catalog[int(pkg_arg)]["package"]
                else:
                    pkg = pkg_arg
                await query.answer(f"Memulai instalasi {pkg}...", show_alert=False)
                await query.edit_message_text(
                    f"[MEMPROSES] <b>Sedang menginstall via pip:</b> <code>{pkg}</code>...\n<i>Mohon tunggu sebentar...</i>",
                    parse_mode=ParseMode.HTML,
                )

                success, out = await asyncio.to_thread(run_pip_install, pkg)
                if success:
                    res_text = f"[BERHASIL] <b>Instalasi Berhasil:</b> <code>{pkg}</code>\n\n<pre>{out[-300:]}</pre>"
                else:
                    res_text = f"[GAGAL] <b>Instalasi Gagal:</b> <code>{pkg}</code>\n\n<pre>{out[-300:]}</pre>"

                kb = [[InlineKeyboardButton("[PLUGIN] Kembali ke Plugins", callback_data="plg:ref")]]
                await query.edit_message_text(
                    res_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
                )
                return

        if data.startswith("fallback:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Fallback approval only permitted for Admin.", show_alert=True)
                return
            parts = data.split(":")
            if len(parts) >= 3:
                action = parts[1]
                fallback_id = parts[2]
            else:
                action = parts[1]
                fallback_id = None

            if not hasattr(self, "_fallback_events") or fallback_id not in self._fallback_events:
                await query.edit_message_text("[PERINGATAN] Request fallback ini sudah kedaluwarsa atau dijawab.")
                return

            tg_event = self._fallback_events[fallback_id]
            tg_result = self._fallback_results[fallback_id]

            if tg_event.is_set():
                await query.edit_message_text(
                    "[PERINGATAN] Request fallback ini sudah kedaluwarsa atau dijawab dari terminal."
                )
                return

            if action == "once":
                tg_result["approved"] = True
                tg_result["always"] = False
                await query.edit_message_text("[BERHASIL] Fallback disetujui (1 Siklus).")
            elif action == "always":
                tg_result["approved"] = True
                tg_result["always"] = True
                await query.edit_message_text("[BERHASIL] Fallback disetujui (Seterusnya).")
            elif action == "reject":
                tg_result["approved"] = False
                tg_result["always"] = False
                await query.edit_message_text("[GAGAL] Fallback ditolak.")

            tg_event.set()

            # Cleanup
            self._fallback_events.pop(fallback_id, None)
            self._fallback_results.pop(fallback_id, None)

        if data.startswith("pause:confirm"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Pause command only permitted for Admin.", show_alert=True)
                return

            parts = data.split(":")
            nonce = parts[2] if len(parts) >= 3 else ""
            reason = "Paused via Telegram"
            duration_hours = None
            duration_desc = ""
            if nonce and hasattr(self, "_active_nonces"):
                entry = self._active_nonces.get(nonce)
                exp = (
                    entry
                    if isinstance(entry, (int, float))
                    else (entry.get("expires", 0) if isinstance(entry, dict) else 0)
                )
                if exp < time.time():
                    await query.edit_message_text("[PERINGATAN] Konfirmasi jeda trading ini sudah kedaluwarsa.")
                    return
                if isinstance(entry, dict):
                    reason = entry.get("reason", reason)
                    duration_hours = entry.get("duration_hours")
                    duration_desc = entry.get("duration_desc", "")
                self._active_nonces.pop(nonce, None)

            from monika.domain.risk.risk_gate import RiskGate
            from monika.infrastructure.database.db import get_session

            gate = RiskGate(self.settings)
            async with get_session() as session:
                await gate.pause_trading(session, reason, duration_hours=duration_hours)
            dur_msg = f"\nDurasi: {duration_desc} (auto-unpause aktif)" if duration_desc else ""
            await query.edit_message_text(
                f"[DIJEDA] *Trading berhasil dijeda.*\nAlasan: {reason}{dur_msg}", parse_mode=ParseMode.MARKDOWN
            )
            return

        if data.startswith("killswitch:confirm"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Kill Switch only permitted for Admin.", show_alert=True)
                return

            parts = data.split(":")
            nonce = parts[2] if len(parts) >= 3 else ""
            if nonce and hasattr(self, "_active_nonces"):
                entry = self._active_nonces.get(nonce)
                if not entry:
                    await query.edit_message_text(
                        "[PERINGATAN] Konfirmasi kill switch ini sudah kedaluwarsa atau telah digunakan."
                    )
                    return
                exp = (
                    entry
                    if isinstance(entry, (int, float))
                    else (entry.get("expires", 0.0) if isinstance(entry, dict) else 0.0)
                )
                if exp < time.time():
                    await query.edit_message_text(
                        "[PERINGATAN] Konfirmasi kill switch ini sudah kedaluwarsa atau telah digunakan."
                    )
                    self._active_nonces.pop(nonce, None)
                    return
                # Single-use: hapus nonce segera setelah divalidasi
                self._active_nonces.pop(nonce, None)

            await query.edit_message_text("[MEMPROSES] Menjalankan kill switch...")
            from monika.application.services.trading_service import TradingService
            from monika.infrastructure.database.db import get_session

            try:
                async with get_session() as session:
                    await TradingService.emergency_kill(session, reason="Telegram kill switch", actor="telegram_admin")
            except Exception as e:
                logger.warning(f"[TelegramBot] TradingService kill switch record: {e}")

            if self.execution_service:
                result = await self.execution_service.kill_switch("Telegram kill switch")
                await query.edit_message_text(
                    f"[BERHENTI] *Kill switch selesai.*\nDitutup: {result['closed']}/{result['total']} posisi",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await query.edit_message_text(
                    "[BERHENTI] Kill switch diaktifkan di database. ExecutionService tidak terhubung."
                )
            return

        if data.startswith("close:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Close position command only permitted for Admin.", show_alert=True)
                return
            parts = data.split(":")
            ticket = int(parts[1])
            volume = float(parts[2]) if len(parts) > 2 and parts[2] != "None" else None
            if self.execution_service:
                result = await self.execution_service.close_position_by_ticket(
                    ticket, requested_by="telegram_admin", reason="Manual close", volume=volume, lots=volume
                )
                if result.get("success"):
                    vol_txt = f" ({volume} lot)" if volume else ""
                    await query.edit_message_text(
                        f"[BERHASIL] Posisi #{ticket}{vol_txt} ditutup.\nProfit: {result.get('profit', 'N/A')}",
                    )
                else:
                    await query.edit_message_text(f"[GAGAL] Gagal tutup: {result.get('error')}")
            else:
                await query.edit_message_text("[PERINGATAN] ExecutionService tidak terhubung.")
            return

        if data.startswith("be:"):
            if not self._is_admin(update):
                await query.answer(
                    "[AKSES DITOLAK] Hanya Admin yang dapat memindahkan SL ke breakeven.", show_alert=True
                )
                return
            ticket = int(data.split(":", 1)[1])
            await query.edit_message_text(f"[MEMPROSES] Menggeser Stop Loss #{ticket} ke breakeven...")
            from monika.application.execution.execution_service import ExecutionService

            sync = ExecutionService(self.settings)
            res = await sync.apply_immediate_breakeven(ticket=ticket)
            if res.get("status") == "success":
                await query.edit_message_text(f"[BERHASIL] SL #{ticket} dipindahkan ke breakeven.")
            else:
                await query.edit_message_text(f"[GAGAL] Gagal breakeven #{ticket}: {res.get('message', 'Unknown')}")
            return

        if data == "bulk_be":
            if not self._is_admin(update):
                await query.answer(
                    "[AKSES DITOLAK] Hanya Admin yang dapat memindahkan SL ke breakeven.", show_alert=True
                )
                return
            await query.edit_message_text("[MEMPROSES] Menggeser seluruh posisi profit ke breakeven...")
            from monika.application.execution.execution_service import ExecutionService

            sync = ExecutionService(self.settings)
            res = await sync.apply_immediate_breakeven(only_profit=True)
            cnt = res.get("breakeven_count", 0)
            await query.edit_message_text(f"[BERHASIL] Bulk Breakeven diterapkan pada {cnt} posisi.")
            return

        if data.startswith("appr_yes:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Approval hanya diizinkan untuk Admin.", show_alert=True)
                return
            token = data.split(":", 1)[1]
            from monika.domain.risk.approval_hub import ApprovalHub

            hub = ApprovalHub.get_instance()
            success, msg = await hub.approve(token, operator=f"tg_{user_id}")
            icon = "✅ [DISETUJUI]" if success else "⚠️ [GAGAL]"
            await query.edit_message_text(f"{icon} {msg}")
            return

        if data.startswith("appr_no:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Penolakan hanya diizinkan untuk Admin.", show_alert=True)
                return
            token = data.split(":", 1)[1]
            from monika.domain.risk.approval_hub import ApprovalHub

            hub = ApprovalHub.get_instance()
            success, msg = await hub.reject(token, operator=f"tg_{user_id}", reason="Ditolak via tombol Telegram")
            await query.edit_message_text(f"❌ [DITOLAK] Permintaan approval #{token[:8]} dibatalkan.")
            return

        if data == "mdl:menu":
            roles = [
                ("jev_telegram_chat", "Chat Bot Assistant"),
                ("debate_judge", "Debate Judge"),
                ("bull_advocate", "Bull Specialist"),
                ("bear_dissent", "Bear Specialist"),
                ("macro_analyst", "Macro Analyst"),
            ]
            kb = [[InlineKeyboardButton(label, callback_data=f"mdl:r:{r}")] for r, label in roles]
            kb.append([InlineKeyboardButton("« Kembali", callback_data="cmd:model")])
            await query.edit_message_text(
                "Pilih <b>Role</b> yang ingin diubah modelnya:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
            )
            return

        if data.startswith("mdl:r:"):
            role = data.split(":", 2)[2]
            models = [
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "claude-3-7-sonnet",
                "llama-3.3-70b-versatile",
            ]
            kb = [[InlineKeyboardButton(m, callback_data=f"mdl:s:{role}:{m}")] for m in models]
            kb.append([InlineKeyboardButton("« Batal", callback_data="mdl:menu")])
            await query.edit_message_text(
                f"Pilih <b>Model</b> untuk role <code>{role}</code>:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
            )
            return

        if data.startswith("mdl:s:"):
            parts = data.split(":", 3)
            role = parts[2]
            model_name = parts[3]
            from monika.infrastructure.providers.runtime_model_registry import RuntimeModelRegistry

            RuntimeModelRegistry.get_instance().set_role_model(role, model_name, slot="primary")
            await query.edit_message_text(
                f"✅ <b>Model Berhasil Diganti</b>\nRole: <code>{role}</code>\nPrimary Model: <code>{model_name}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        if data == "mdl:reset_all":
            from monika.infrastructure.providers.runtime_model_registry import RuntimeModelRegistry

            RuntimeModelRegistry.get_instance().clear_overrides()
            await query.edit_message_text(
                "♻️ Seluruh model override telah direset ke default settings.yaml.", parse_mode=ParseMode.HTML
            )
            return

        if data.startswith("confirm:") or data.startswith("approve:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Action confirmation only permitted for Admin.", show_alert=True)
                return
            action_id = data.split(":", 1)[1]

            from monika.domain.risk.approval_hub import ApprovalHub

            hub = ApprovalHub.get_instance()
            req = hub.get_request(action_id)
            if req:
                await query.edit_message_text(f"[MEMPROSES] Mengeksekusi via ApprovalHub [{action_id}]...")
                success, msg = await hub.approve(action_id, operator=f"tg_{user_id}")
                if success and req.request_type == "trade_proposal" and self.execution_service:
                    try:
                        trade = req.details or {}
                        symbol = req.symbol
                        action_type = (req.action_type or "").lower().strip()
                        lots = float(trade.get("lots") or trade.get("volume") or 0.0)

                        if action_type in ("close", "close_position", "exit", "flat"):
                            ticket = trade.get("ticket") or trade.get("mt5_ticket")
                            if ticket:
                                res = await self.execution_service.close_position_by_ticket(
                                    ticket=int(ticket),
                                    requested_by=f"tg_{user_id}",
                                    reason=f"Voice approval close #{ticket}",
                                    lots=lots if lots > 0 else None,
                                )
                                if res.get("success"):
                                    await query.edit_message_text(
                                        f"[BERHASIL] Posisi #{ticket} ({symbol}) berhasil ditutup."
                                    )
                                else:
                                    await query.edit_message_text(
                                        f"[GAGAL] Gagal menutup #{ticket}: {res.get('error', 'Unknown error')}"
                                    )
                            else:
                                res = await self.execution_service.close_positions_batch(
                                    filter_type="all",
                                    requested_by=f"tg_{user_id}",
                                    reason=f"Voice approval close symbol {symbol}",
                                    symbol=symbol if symbol and symbol != "ALL" else None,
                                )
                                closed = res.get("closed_tickets", [])
                                failed = res.get("failed_tickets", [])
                                if closed:
                                    await query.edit_message_text(
                                        f"[BERHASIL] Ditutup {len(closed)} posisi untuk {symbol}."
                                    )
                                elif failed:
                                    await query.edit_message_text(f"[GAGAL] Gagal menutup posisi: {res.get('errors')}")
                                else:
                                    await query.edit_message_text(f"[INFO] Tidak ada posisi terbuka untuk {symbol}.")
                            return

                        direction = action_type
                        if direction not in ("buy", "sell"):
                            await query.edit_message_text(
                                f"[GAGAL] Action type '{action_type}' tidak valid untuk eksekusi order."
                            )
                            return

                        effective_lots = lots if lots > 0 else 0.01
                        sl = float(trade["stop_loss"]) if trade.get("stop_loss") is not None else None
                        tp = float(trade["take_profit"]) if trade.get("take_profit") is not None else None

                        from monika.infrastructure.database.db import get_session
                        from monika.infrastructure.database.models import AssetAnalysis

                        async with get_session() as session:
                            entry_zone_dict: dict[str, Any] = {"type": "market"}
                            if effective_lots > 0:
                                entry_zone_dict["lots"] = effective_lots
                                entry_zone_dict["lot_size"] = effective_lots
                            analysis = AssetAnalysis(
                                symbol=symbol,
                                generated_at=datetime.now(timezone.utc),
                                decision=direction,
                                confidence=0.85,
                                entry_zone=json.dumps(entry_zone_dict),
                                stop_loss=sl,
                                take_profit=tp,
                                rationale=f"Voice Note Approval Execution: {trade.get('transcript', '')}",
                            )
                            session.add(analysis)
                            await session.flush()
                            exec_kwargs = {}
                            if effective_lots > 0:
                                exec_kwargs["lots"] = effective_lots
                                exec_kwargs["lot_size"] = effective_lots
                            res = await self.execution_service.execute_analysis(session, analysis, **exec_kwargs)
                            if res.executed:
                                await query.edit_message_text(
                                    f"[BERHASIL] Order {res.decision.upper()} {res.executed_lots} lot {res.symbol} berhasil dieksekusi!\n"
                                    f"Harga: {res.executed_price} | Ticket: #{res.mt5_ticket}"
                                )
                            else:
                                reasons = "; ".join(res.risk_rejection_reasons) or res.mt5_error or "Ditolak RiskGate"
                                await query.edit_message_text(f"[GAGAL] Order diblokir RiskGate: {reasons}")
                    except Exception as exec_err:
                        logger.error(f"[Bot] Failed to execute approved voice order: {exec_err}", exc_info=True)
                        await query.edit_message_text(f"[PERINGATAN] Approval sukses tetapi eksekusi gagal: {exec_err}")
                else:
                    await query.edit_message_text(f"{'[BERHASIL]' if success else '[GAGAL]'} {msg}")
                return

            agent = await self._resolve_action_agent(user_id, action_id, query)
            if not agent:
                if action_id.isdigit() and self.execution_service:
                    await query.edit_message_text(f"[MEMPROSES] Mengeksekusi analisis #{action_id}...")
                    try:
                        res = await self.execution_service.execute_by_analysis_id(int(action_id))
                        await query.edit_message_text(
                            f"[BERHASIL] {res.summary() if hasattr(res, 'summary') else str(res)}"
                        )
                    except Exception as exec_err:
                        await query.edit_message_text(f"[GAGAL] Gagal eksekusi #{action_id}: {exec_err}")
                    return
                await query.edit_message_text("[GAGAL] Sesi tidak ditemukan.")
                return
            await query.edit_message_text("[MEMPROSES] Mengeksekusi...")
            success, msg = await agent.confirm_action(action_id)
            await query.edit_message_text(msg)
            return

        if data.startswith("allow_session:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Session authorization only permitted for Admin.", show_alert=True)
                return
            action_id = data.split(":", 1)[1]
            agent = await self._resolve_action_agent(user_id, action_id, query)
            if not agent:
                if action_id.isdigit() and self.execution_service:
                    await query.edit_message_text(f"[MEMPROSES] Mengeksekusi analisis #{action_id}...")
                    try:
                        res = await self.execution_service.execute_by_analysis_id(int(action_id))
                        await query.edit_message_text(
                            f"[BERHASIL] {res.summary() if hasattr(res, 'summary') else str(res)}"
                        )
                    except Exception as exec_err:
                        await query.edit_message_text(f"[GAGAL] Gagal eksekusi #{action_id}: {exec_err}")
                    return
                await query.edit_message_text("[GAGAL] Sesi tidak ditemukan.")
                return
            await query.edit_message_text("[MEMPROSES] Mengeksekusi dan mengaktifkan izin sesi (4h)...")
            success, msg = await agent.approve_for_session(action_id)
            await query.edit_message_text(msg)
            return

        if data.startswith("reject:"):
            if not self._is_admin(update):
                await query.answer("[AKSES DITOLAK] Action rejection only permitted for Admin.", show_alert=True)
                return
            action_id = data.split(":", 1)[1]

            from monika.domain.risk.approval_hub import ApprovalHub

            hub = ApprovalHub.get_instance()
            if hub.get_request(action_id):
                success, msg = await hub.reject(action_id, operator=f"tg_{user_id}", reason="Dibatalkan via Telegram")
                await query.edit_message_text(f"[GAGAL] Permintaan [{action_id}] telah dibatalkan.")
                return

            agent = await self._resolve_action_agent(user_id, action_id, query)
            if not agent:
                if action_id.isdigit():
                    from sqlalchemy import update as sql_update

                    from monika.infrastructure.database.db import get_session
                    from monika.infrastructure.database.models import ActivityLog, AssetAnalysis, PaperTradeRecord

                    async with get_session() as session:
                        session.add(
                            ActivityLog(
                                category="trading",
                                description=f"Trade proposal #{action_id} REJECTED by admin via Telegram inline button",
                                actor="telegram_admin",
                            )
                        )
                        try:
                            await session.execute(
                                sql_update(AssetAnalysis)
                                .where(AssetAnalysis.id == int(action_id))
                                .values(
                                    execution_status="rejected", execution_notes="Rejected via Telegram inline button"
                                )
                            )
                            await session.execute(
                                sql_update(PaperTradeRecord)
                                .where(PaperTradeRecord.analysis_id == int(action_id))
                                .where(PaperTradeRecord.status == "open")
                                .values(
                                    status="closed",
                                    closed_at=datetime.now(timezone.utc),
                                    exit_reason="rejected_by_admin",
                                    pnl_pct=0.0,
                                )
                            )
                        except Exception:
                            pass
                        await session.commit()
                    await query.edit_message_text(f"[GAGAL] Analisis #{action_id} ditolak.")
                    return
                await query.edit_message_text("[GAGAL] Sesi tidak ditemukan.")
                return
            msg = await agent.reject_action(action_id)
            await query.edit_message_text(f"[GAGAL] {msg}")
            return

        await query.edit_message_text("[?] Callback tidak dikenali.")

    # ------------------------------------------------------------------
    # Data builders (read-only DB queries)
    # ------------------------------------------------------------------


__all__ = ["TelegramCallbackHandlerMixin"]
