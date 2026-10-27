# ==============================================================================
# File: interfaces/telegram/handlers/admin_commands.py
# ==============================================================================

"""
Plugin, Knowledge, Cron, and Operator Administration Commands Group for Telegram Bot.
Handles plugin lifecycles, memory inspect, strategy tuning, cron tasks, and rollback operations.
"""

from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.base import _TelegramBotMixinBase

logger = logging.getLogger(__name__)


class TelegramAdminCommandsMixin(_TelegramBotMixinBase):
    """Mixin providing plugin management, model config, and admin state command handlers for TelegramBot."""

    async def _cmd_counterfactual(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        args = ctx.args or []
        if not args:
            await update.message.reply_text(
                "Usage: `/counterfactual <trade_id> [sl_pips_delta] [tp_pips_delta]`\nContoh: `/counterfactual 123 10.0` (simulasi jika SL 10 pips lebih lebar)",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        try:
            trade_id = int(args[0])
            sl_delta = float(args[1]) if len(args) > 1 else 10.0
            tp_delta = float(args[2]) if len(args) > 2 else 0.0
            from monika.application.analysis.memory.counterfactual_simulator import CounterfactualSimulator
            from monika.infrastructure.database.db import get_session

            sim = CounterfactualSimulator()
            async with get_session() as sess:
                res = await sim.simulate_single_trade_counterfactual(sess, trade_id, sl_delta, tp_delta)
            if res.get("status") == "error":
                await update.message.reply_text(f"[GAGAL] {res.get('message')}")
                return
            orig = res.get("original", {})
            cf = res.get("counterfactual", {})
            cf_pnl_diff = cf.get("pnl_diff")
            pnl_icon = "[AKTIF]" if (cf_pnl_diff is not None and cf_pnl_diff >= 0) else "[KRITIS]"
            orig_pnl = f"${orig['pnl']:.2f}" if orig.get("pnl") is not None else "N/A"
            est_pnl = f"${cf['estimated_pnl']:.2f}" if cf.get("estimated_pnl") is not None else "N/A"
            pnl_diff = f"{pnl_icon} `${cf_pnl_diff:+.2f}`" if cf_pnl_diff is not None else "N/A"
            msg = (
                f"[RISET] *Counterfactual Replay: Trade #{trade_id} ({res.get('symbol')} {res.get('direction')})*\n"
                f"Entry: `{res.get('entry_price')}`\n\n"
                f"[LAPORAN] *Hasil Asli:*\n"
                f"• SL: `{orig.get('stop_loss')}` | TP: `{orig.get('take_profit')}`\n"
                f"• Exit Reason: `{orig.get('exit_reason')}`\n"
                f"• Realized PnL: `{orig_pnl}`\n\n"
                f"[UJI COBA] *Skenario Counterfactual (SL +{sl_delta} pips):*\n"
                f"• New SL: `{cf.get('new_stop_loss')}`\n"
                f"• Survived SL: `{'YA' if cf.get('survived_sl') else 'TIDAK'}`\n"
                f"• Outcome: `{cf.get('outcome')}`\n"
                f"• Est. PnL: `{est_pnl}`\n"
                f"• PnL Delta: {pnl_diff}\n\n"
                f"[CATATAN] *Catatan:* {res.get('notes')}"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Counterfactual command error: {e}", exc_info=True)
            await update.message.reply_text(f"[ERROR] Gagal menjalankan counterfactual: {e}")

    async def _cmd_chronicle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        args = ctx.args or []
        month = args[0] if args else None
        year = int(args[1]) if len(args) > 1 else None
        from monika.application.analysis.tools.handlers.trade_intel import handle_get_market_chronicle

        res = await handle_get_market_chronicle({"month": month, "year": year or 2026, "limit": 10})
        chronicles = res.get("chronicles", [])
        if not chronicles:
            await update.message.reply_text(
                f"[LOG] Tidak ada catatan chronicle untuk periode {month or 'terkini'} {year or ''}."
            )
            return
        lines = [f"[LOG] *Market Chronicle ({month or 'Terkini'} {year or res.get('year')}):*\n"]
        for c in chronicles[:8]:
            dt = str(c.get("event_date", ""))[:10]
            cat = str(c.get("category", "")).upper()
            hl = c.get("headline", "")
            lines.append(f"• `[{dt}]` *[{cat}]* {hl}")
            if c.get("narrative"):
                lines.append(f"  _{c.get('narrative')[:120]}..._\n")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_export_chat(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        import io
        import json

        from sqlalchemy import select

        from monika.application.analysis.memory.sharegpt_exporter import ShareGptExporter
        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import TelegramConversation

        user_id = str(update.effective_user.id)
        limit = 50
        if ctx.args:
            try:
                limit = int(ctx.args[0])
            except ValueError:
                pass

        async with get_session() as session:
            rows = (
                (
                    await session.execute(
                        select(TelegramConversation)
                        .where(TelegramConversation.telegram_user_id == user_id)
                        .order_by(TelegramConversation.timestamp.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

        if not rows:
            await update.message.reply_text("Tidak ada riwayat percakapan untuk diekspor.")
            return

        msgs = [{"role": r.role, "content": r.message} for r in reversed(rows)]
        sharegpt_data = ShareGptExporter.to_sharegpt_format(msgs)

        json_bytes = json.dumps(sharegpt_data, indent=2, ensure_ascii=False).encode("utf-8")
        doc = io.BytesIO(json_bytes)
        doc.name = f"chat_export_{user_id}.json"
        await update.message.reply_document(
            document=doc,
            caption=f"[KIRIM] *ShareGPT Trajectory Export* ({len(sharegpt_data)} turns)",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_undo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        from sqlalchemy import delete, select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import TelegramConversation

        user_id = str(update.effective_user.id)
        async with get_session() as session:
            recent = (
                (
                    await session.execute(
                        select(TelegramConversation)
                        .where(TelegramConversation.telegram_user_id == user_id)
                        .order_by(TelegramConversation.timestamp.desc())
                        .limit(2)
                    )
                )
                .scalars()
                .all()
            )

            if not recent:
                await update.message.reply_text("Tidak ada pesan sebelumnya yang dapat di-undo.")
                return

            ids_to_del = [r.id for r in recent]
            await session.execute(delete(TelegramConversation).where(TelegramConversation.id.in_(ids_to_del)))
            await session.commit()

        try:
            from monika.application.agent.state_rewind import StateRewindManager
            from monika.infrastructure.database.session_db_wal import DEFAULT_SESSION_DB_PATH, SessionDbWal

            if DEFAULT_SESSION_DB_PATH.exists():
                wal_db = SessionDbWal(DEFAULT_SESSION_DB_PATH)
                rewinder = StateRewindManager(wal_db)
                await asyncio.to_thread(rewinder.rewind_session, user_id)
        except Exception:
            pass

        await update.message.reply_text(
            "↩ *Percakapan Berhasil Di-Undo*\n"
            f"• Pesan terakhir ({len(ids_to_del)} giliran) dihapus dari memori konteks.\n"
            "• _Catatan: Transaksi broker MT5 tetap permanen di ledger._",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_backup(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        from monika.infrastructure.database.backup import create_backup

        res = await create_backup(self.settings, force=True)
        if res.get("success"):
            text = (
                f"[SIMPAN] *Database Backup Sukses!*\n"
                f"• File: `{res.get('backup_file')}`\n"
                f"• Ukuran: `{res.get('size_mb')} MB`\n"
                f"• Waktu: `{res.get('timestamp')}`"
            )
        else:
            text = f"[GAGAL] *Database Backup Gagal:*\n`{res.get('error') or res.get('reason')}`"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_playbooks(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_playbooks_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_rollback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        if not ctx.args:
            await update.message.reply_text(
                "Format: `/rollback <playbook_name>`\nContoh: `/rollback eurusd_trend`", parse_mode=ParseMode.MARKDOWN
            )
            return
        name = ctx.args[0].strip()
        text = await self._build_rollback_text(name)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_crystallized(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_crystallized_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_cron(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            from monika.application.analysis.tools.domain.cron_tool import (
                DEFAULT_CRON_FILE,
                CronJobRecord,
                CronRegistry,
            )

            registry = CronRegistry(DEFAULT_CRON_FILE)
            args = ctx.args or []
            subcmd = args[0].lower() if args else "list"

            if subcmd == "list":
                jobs = registry.list_jobs()
                if not jobs:
                    await update.message.reply_text(
                        "[WAKTU] *Universal Cron Schedules*\n\nTidak ada jadwal cron aktif.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return
                lines = [f"[WAKTU] *Universal Cron Schedules ({len(jobs)} Active)*\n"]
                for j in jobs:
                    status = "[BERHASIL]" if j.enabled else "[DIJEDA]"
                    lines.append(
                        f"{status} *{j.name}* (`{j.cron_expression}`)\n  _{j.description}_\n  Prompt: `{j.instruction[:60]}...`\n"
                    )
                lines.append("Gunakan `/cron add <name> <expr> <prompt>` atau `/cron remove <name>`.")
                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
            elif subcmd == "remove" and len(args) > 1:
                name = args[1].strip()
                ok = registry.remove_job(name)
                if ok:
                    await update.message.reply_text(
                        f"[BERHASIL] Jadwal cron `{name}` berhasil dihapus.", parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await update.message.reply_text(
                        f"[GAGAL] Jadwal cron `{name}` tidak ditemukan.", parse_mode=ParseMode.MARKDOWN
                    )
            elif subcmd == "add" and len(args) >= 4:
                name = args[1].strip()
                expr = args[2].strip()
                prompt = " ".join(args[3:]).strip()
                job = CronJobRecord(
                    name=name,
                    cron_expression=expr,
                    instruction=prompt,
                    description=f"Telegram: {prompt[:40]}",
                    enabled=True,
                    created_at=time.time(),
                )
                registry.add_job(job)
                await update.message.reply_text(
                    f"[BERHASIL] Jadwal cron `{name}` (`{expr}`) berhasil didaftarkan.", parse_mode=ParseMode.MARKDOWN
                )
            else:
                help_text = (
                    "[WAKTU] *Penggunaan Perintah Cron*\n\n"
                    "• `/cron` atau `/cron list` : Tampilkan seluruh jadwal\n"
                    "• `/cron add <nama> <cron_expr> <prompt>` : Tambah jadwal baru\n"
                    "  _Contoh:_ `/cron add cot_scan */30 * * * * Jalankan audit COT_\n"
                    "• `/cron remove <nama>` : Hapus jadwal yang ada"
                )
                await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as exc:
            await update.message.reply_text(f"[GAGAL] Error mengevaluasi perintah cron: {exc}")

    async def _cmd_model(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Interactive model routing inspection and hot-swapping (/model)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            from monika.core.config.settings import get_settings
            from monika.infrastructure.providers.runtime_model_registry import RuntimeModelRegistry

            registry = RuntimeModelRegistry.get_instance()
            args = ctx.args or []

            if not args or args[0].lower() == "list":
                settings = get_settings()
                task_roles = settings.get("llm", {}).get("task_roles", {})
                overrides = registry.get_all_overrides()

                lines = ["[ASISTEN AI] <b>Model Routing & Task Roles</b>\n"]
                all_roles = sorted(set(list(task_roles.keys()) + list(overrides.keys())))

                for r in all_roles:
                    cfg_role = task_roles.get(r, {})
                    def_primary = cfg_role.get("primary", "unknown") if isinstance(cfg_role, dict) else str(cfg_role)
                    def_fallback = cfg_role.get("fallback_1", "-") if isinstance(cfg_role, dict) else "-"

                    ovr = overrides.get(r, {})
                    cur_primary = ovr.get("primary", def_primary)
                    cur_fallback = ovr.get("fallback_1", def_fallback)

                    is_overridden = bool(ovr)
                    marker = "[KILAT]" if is_overridden else "•"
                    lines.append(
                        f"{marker} <b>{r}</b>:\n  Primary: <code>{cur_primary}</code>\n  Fallback: <code>{cur_fallback}</code>"
                    )

                lines.append(
                    "\n<b>Penggunaan:</b>\n• <code>/model set &lt;role&gt; &lt;model_name&gt; [primary|fallback_1]</code>\n• <code>/model reset [role]</code>"
                )
                kb = [
                    [
                        InlineKeyboardButton("🔄 Ganti Role Model", callback_data="mdl:menu"),
                        InlineKeyboardButton("♻️ Reset Overrides", callback_data="mdl:reset_all"),
                    ]
                ]
                await update.message.reply_text(
                    "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
                )
                return

            subcmd = args[0].lower()
            if subcmd == "set" and len(args) >= 3:
                role = args[1].strip()
                model_name = args[2].strip()
                slot = args[3].strip().lower() if len(args) > 3 else "primary"
                if slot not in ("primary", "fallback_1", "fallback_2"):
                    slot = "primary"

                registry.set_role_model(role, model_name, slot=slot)
                await update.message.reply_text(
                    f"[BERHASIL] <b>Model Hot-Swapped</b>\nRole: <code>{role}</code>\nSlot: <code>{slot}</code>\nModel: <code>{model_name}</code>",
                    parse_mode=ParseMode.HTML,
                )
            elif subcmd == "reset":
                role = args[1].strip() if len(args) > 1 else None
                registry.clear_overrides(role)
                target_desc = f"role '{role}'" if role else "seluruh role"
                await update.message.reply_text(
                    f"[SINKRONISASI] <b>Model Overrides Direset</b>\nReset {target_desc} kembali ke konfigurasi default settings.yaml.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.message.reply_text(
                    "[GAGAL] Format salah. Gunakan:\n• <code>/model</code> (tampilkan semua role)\n• <code>/model set &lt;role&gt; &lt;model&gt; [slot]</code>\n• <code>/model reset [role]</code>",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            logger.error(f"Error handling /model command: {exc}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Error mengevaluasi /model: {exc}")

    async def _cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        try:
            from monika.application.skills.loader import list_skills

            all_s = list_skills()
            playbooks = [s for s in all_s if "playbook" in s.lower() or s.startswith("alpha_")]
            core = [s for s in all_s if s not in playbooks]

            lines = [
                f"[KEYAKINAN] <b>Autonomous Skills & Playbooks ({len(all_s)} Total)</b>\n",
                f"<b>Core Prompt Skills ({len(core)}):</b>",
            ]
            for s in core[:8]:
                lines.append(f"• <code>{s}</code>")
            if len(core) > 8:
                lines.append(f"<i>...dan {len(core) - 8} lainnya</i>")

            lines.append(f"\n<b>Playbook Strategies ({len(playbooks)}):</b>")
            for p in playbooks[:8]:
                lines.append(f"• <code>{p}</code>")
            if len(playbooks) > 8:
                lines.append(f"<i>...dan {len(playbooks) - 8} lainnya</i>")

            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error listing skills: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal memuat daftar skills: {e}")

    async def _cmd_plugins(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        try:
            from monika.application.plugins.engine.installer import list_all_plugins_status

            plugins = list_all_plugins_status()
            if not plugins:
                await update.message.reply_text("[INFORMASI] Belum ada modul plugin yang terdaftar di sistem.")
                return

            text = self._build_plugins_text(plugins)
            markup = self._build_plugins_keyboard(plugins)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error listing plugins in Telegram: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal memuat status plugins: {e}")

    async def _cmd_plugin_catalog(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        try:
            from monika.application.plugins.engine.installer import get_community_catalog

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
            await update.message.reply_text(
                "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Error viewing plugin catalog: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal memuat katalog plugin: {e}")

    async def _cmd_plugin_install(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text(
                "[INFORMASI] Format: <code>/plugin_install &lt;package_name&gt;</code>\nContoh: <code>/plugin_install monika-plugin-deepseek</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        pkg = ctx.args[0].strip()
        from monika.application.plugins.engine.installer import run_pip_install, validate_package_spec

        valid, err = validate_package_spec(pkg)
        if not valid:
            await update.message.reply_text(f"[GAGAL] <b>Validasi Paket Ditolak:</b>\n{err}", parse_mode=ParseMode.HTML)
            return

        msg = await update.message.reply_text(
            f"[MEMPROSES] <b>Menginstall plugin via pip:</b> <code>{pkg}</code>...\n<i>Mohon tunggu sebentar...</i>",
            parse_mode=ParseMode.HTML,
        )
        success, out = await asyncio.to_thread(run_pip_install, pkg)

        status_icon = "[BERHASIL]" if success else "[GAGAL]"
        status_word = "Berhasil" if success else "Gagal"
        tail_out = out[-400:] if len(out) > 400 else out
        await msg.edit_text(
            f"{status_icon} <b>Instalasi {status_word}:</b> <code>{pkg}</code>\n\n<pre>{tail_out}</pre>",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_plugin_uninstall(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text(
                "[INFORMASI] Format: <code>/plugin_uninstall &lt;package_name&gt;</code>", parse_mode=ParseMode.HTML
            )
            return

        pkg = ctx.args[0].strip()
        from monika.application.plugins.engine.installer import run_pip_uninstall

        msg = await update.message.reply_text(
            f"[MEMPROSES] <b>Menghapus paket via pip:</b> <code>{pkg}</code>...", parse_mode=ParseMode.HTML
        )
        success, out = await asyncio.to_thread(run_pip_uninstall, pkg)
        status_icon = "[BERHASIL]" if success else "[GAGAL]"
        await msg.edit_text(
            f"{status_icon} <b>Uninstall {'Berhasil' if success else 'Gagal'}:</b> <code>{pkg}</code>",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_plugin_toggle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text(
                "[INFORMASI] Format: <code>/plugin_toggle &lt;plugin_id&gt;</code>", parse_mode=ParseMode.HTML
            )
            return

        plugin_id = ctx.args[0].strip()
        from monika.application.plugins.engine.installer import list_all_plugins_status, toggle_plugin_state

        plugins = {p["id"]: p for p in list_all_plugins_status()}
        if plugin_id in plugins:
            p = plugins[plugin_id]
            if not p["can_toggle"]:
                await update.message.reply_text("[PERINGATAN] Komponen inti (core) tidak dapat dinonaktifkan.")
                return
            new_state = not p["enabled"]
            ok, res_msg = toggle_plugin_state(plugin_id, p["category"], new_state)
            await update.message.reply_text(f"{'[AKTIF]' if new_state else '[NONAKTIF]'} {res_msg}")
        else:
            await update.message.reply_text(
                f"[GAGAL] Plugin '<code>{plugin_id}</code>' tidak ditemukan.", parse_mode=ParseMode.HTML
            )

    async def _cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        query = " ".join(ctx.args).strip() if ctx.args else ""
        from sqlalchemy import or_, select

        from monika.infrastructure.database.db import AsyncSessionLocal
        from monika.infrastructure.database.models import DecisionReflection

        try:
            async with AsyncSessionLocal() as session:
                if query:
                    q = (
                        select(DecisionReflection)
                        .where(
                            or_(
                                DecisionReflection.symbol.ilike(f"%{query}%"),
                                DecisionReflection.reflection_text.ilike(f"%{query}%"),
                                DecisionReflection.specific_lesson.ilike(f"%{query}%"),
                            )
                        )
                        .order_by(DecisionReflection.id.desc())
                        .limit(5)
                    )
                else:
                    q = select(DecisionReflection).order_by(DecisionReflection.id.desc()).limit(5)

                reflections = (await session.execute(q)).scalars().all()

                if not reflections:
                    await update.message.reply_text("[INFORMASI] Belum ada rekaman refleksi memori yang cocok.")
                    return

                lines = [f"[PASAR] <b>Autonomous Memory Vault ({len(reflections)} Terkini)</b>\n"]
                for r in reflections:
                    res_emoji = "[AKTIF]" if (r.outcome_pnl_usd or 0) > 0 else "[KRITIS]"
                    pnl_str = f"${r.outcome_pnl_usd:+,.2f}" if r.outcome_pnl_usd is not None else "N/A"
                    lesson_snippet = r.specific_lesson or (
                        r.reflection_text[:120] if r.reflection_text else "No lesson recorded."
                    )
                    safe_sym = html.escape(str(r.symbol or ""))
                    safe_dec = html.escape(str(r.decision or "").upper())
                    safe_lesson = html.escape(lesson_snippet or "")
                    lines.append(
                        f"{res_emoji} <b>[{safe_sym}]</b> {safe_dec} | PnL: <code>{pnl_str}</code>\n"
                        f"[CATATAN] <i>{safe_lesson}</i>\n"
                    )

                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error retrieving memory: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal membaca memori: {e}")

    async def _cmd_strategies(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        from sqlalchemy import select

        from monika.infrastructure.database.db import AsyncSessionLocal
        from monika.infrastructure.database.models import PlaybookRuleAttribution

        try:
            async with AsyncSessionLocal() as session:
                rules = (
                    (
                        await session.execute(
                            select(PlaybookRuleAttribution)
                            .order_by(PlaybookRuleAttribution.times_triggered.desc())
                            .limit(10)
                        )
                    )
                    .scalars()
                    .all()
                )

                if not rules:
                    await update.message.reply_text(
                        "[INFORMASI] Belum ada aturan playbook / strategi empiris terdaftar di DB."
                    )
                    return

                lines = ["[DEBAT] <b>Empirical Playbook Strategies & Rules:</b>\n"]
                for rule in rules:
                    wr = (rule.win_rate or 0.0) * 100
                    pnl = rule.total_pnl or 0.0
                    rule_snippet = (rule.rule_text[:90] + "...") if len(rule.rule_text) > 90 else rule.rule_text
                    safe_sym = html.escape(str(rule.symbol or ""))
                    safe_status = html.escape(str(rule.status or "").upper())
                    safe_rule = html.escape(rule_snippet or "")
                    lines.append(
                        f"• <b>[{safe_sym}]</b> <code>{safe_status}</code>\n"
                        f"  Rule: <i>{safe_rule}</i>\n"
                        f"  Triggers: <b>{rule.times_triggered}</b> | WR: <b>{wr:.1f}%</b> | PnL: <code>${pnl:+,.2f}</code>\n"
                    )

                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error retrieving strategies: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal memuat playbook strategies: {e}")


__all__ = ["TelegramAdminCommandsMixin"]
