# ==============================================================================
# File: telegram_bot/bot.py
# ==============================================================================

"""
Bot Telegram — Entry point dan dispatcher.

Menggunakan python-telegram-bot v22.x (async-native).

Arsitektur Handler:
  /start, /help   → Respons teks instan
  /status         → Status portofolio & risiko dari DB
  /positions      → Posisi terbuka & PnL
  /brief          → Fundamental brief terkini
  /history        → 10 aktivitas terakhir
  /risk           → Status risiko (PnL harian, drawdown, status pause)
  /vix            → Data VIX terkini
  /pause [reason] → [Admin] Pause trading
  /resume         → [Admin] Resume trading
  /kill           → [Admin] Tutup semua posisi darurat & pause
  /close <ticket> → [Admin] Tutup posisi tertentu (butuh konfirmasi)
  /run            → [Admin] Paksa eksekusi siklus analisis
  <teks>          → Mode chat dengan asisten AI (ChatAgent)
  
Callback Queries:
  confirm:<id>   → Eksekusi aksi pending
  reject:<id>    → Tolak aksi pending
  close:<ticket> → Konfirmasi penutupan perintah /close
  cancel         → Batalkan operasi pending
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode, ChatAction
from telegram_bot.sanitizer import sanitize_telegram_html
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
logger = logging.getLogger("TradingAgent.Telegram")

class IgnoreNetworkErrorFilter(logging.Filter):
    def filter(self, record):
        if record.exc_info:
            err_type = str(record.exc_info[0])
            err_msg = str(record.exc_info[1])
            if "NetworkError" in err_type or "Bad Gateway" in err_msg:
                return False
        return True

logging.getLogger("telegram.ext.Updater").addFilter(IgnoreNetworkErrorFilter())


class TelegramBot:
    """
    Bot Telegram operasional untuk AI Trading Agent.

    Penggunaan:
        bot = TelegramBot(settings, execution_service, cycle_scheduler)
        await bot.start()   # Blocking sampai dihentikan
    """

    def __init__(
        self,
        settings: dict,
        execution_service=None,
        cycle_scheduler=None,
    ):
        self.settings            = settings
        self.execution_service   = execution_service
        self.cycle_scheduler     = cycle_scheduler
        self._activity_log: Optional[Any] = None

        self.token         = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.admin_chat_id = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", 0) or 0)

        # Parse allowed users whitelist
        raw_allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        self.allowed_user_ids: set[int] = set()
        if raw_allowed.strip():
            for uid in raw_allowed.split(","):
                uid = uid.strip()
                if uid.isdigit() or (uid.startswith("-") and uid[1:].isdigit()):
                    self.allowed_user_ids.add(int(uid))
        if self.admin_chat_id:
            self.allowed_user_ids.add(self.admin_chat_id)

        # Per-user ChatAgent instances (lazy init)
        from telegram_bot.chat_agent import ChatAgent
        from telegram_bot.topic_manager import TopicManager
        from telegram_bot.voice_handler import VoiceHandler
        self._chat_agents: dict[Any, ChatAgent] = {}
        self.topic_manager = TopicManager()
        self.voice_handler = VoiceHandler(bot=self, settings=self.settings)

        from telegram_bot.command_router import CommandRouter
        self._router = CommandRouter(
            admin_chat_id=self.admin_chat_id,
            allowed_user_ids=self.allowed_user_ids,
        )

        self._is_running: bool = False

        if not self.token or self.token.startswith("your_"):
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot will not connect")
            self._app = None
        else:
            self._app = (
                ApplicationBuilder()
                .token(self.token)
                .build()
            )
            self._register_handlers()

    @property
    def is_running(self) -> bool:
        """Returns True if TelegramBot polling loop is active."""
        return self._is_running and self._app is not None

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        app = self._app
        if not app:
            return
        # Direct commands
        app.add_handler(CommandHandler("start",     self._cmd_start))
        app.add_handler(CommandHandler("help",      self._cmd_help))
        app.add_handler(CommandHandler("status",    self._cmd_status))
        app.add_handler(CommandHandler("positions", self._cmd_positions))
        app.add_handler(CommandHandler("brief",     self._cmd_brief))
        app.add_handler(CommandHandler("analysis",  self._cmd_analysis))
        app.add_handler(CommandHandler("history",   self._cmd_history))
        app.add_handler(CommandHandler("risk",      self._cmd_risk))
        app.add_handler(CommandHandler("vix",       self._cmd_vix))
        app.add_handler(CommandHandler("tokens",    self._cmd_tokens))
        app.add_handler(CommandHandler("report",    self._cmd_report))
        app.add_handler(CommandHandler("tearsheet", self._cmd_tearsheet))
        app.add_handler(CommandHandler("stats",     self._cmd_stats))
        app.add_handler(CommandHandler("cost",      self._cmd_cost))
        app.add_handler(CommandHandler("credits",   self._cmd_credits))
        app.add_handler(CommandHandler("edge",      self._cmd_edge))
        app.add_handler(CommandHandler("calibration", self._cmd_calibration))
        app.add_handler(CommandHandler("intel",       self._cmd_intel))
        app.add_handler(CommandHandler("archive_intel", self._cmd_archive_intel))
        app.add_handler(CommandHandler("regime",      self._cmd_regime))
        app.add_handler(CommandHandler("audit",       self._cmd_audit))
        # Admin commands
        app.add_handler(CommandHandler("pause",  self._cmd_pause))
        app.add_handler(CommandHandler("resume", self._cmd_resume))
        app.add_handler(CommandHandler("unsuspend", self._cmd_unsuspend))
        app.add_handler(CommandHandler("kill",   self._cmd_kill))
        app.add_handler(CommandHandler("emergency", self._cmd_emergency))
        app.add_handler(CommandHandler("close",  self._cmd_close))
        app.add_handler(CommandHandler("closeall", self._cmd_closeall))
        app.add_handler(CommandHandler("override", self._cmd_override))
        app.add_handler(CommandHandler("run",    self._cmd_run))
        app.add_handler(CommandHandler("backtest", self._cmd_backtest))
        app.add_handler(CommandHandler("approve", self._cmd_approve))
        app.add_handler(CommandHandler("reject",  self._cmd_reject))
        app.add_handler(CommandHandler("steer",   self._cmd_steer))
        app.add_handler(CommandHandler("interrupt", self._cmd_interrupt))
        app.add_handler(CommandHandler("resume_proposals", self._cmd_resume_proposals))
        app.add_handler(CommandHandler("calendar", self._cmd_calendar))
        app.add_handler(CommandHandler("skills", self._cmd_skills))
        app.add_handler(CommandHandler("plugins", self._cmd_plugins))
        app.add_handler(CommandHandler("plugin_catalog", self._cmd_plugin_catalog))
        app.add_handler(CommandHandler("plugin_install", self._cmd_plugin_install))
        app.add_handler(CommandHandler("plugin_uninstall", self._cmd_plugin_uninstall))
        app.add_handler(CommandHandler("plugin_toggle", self._cmd_plugin_toggle))
        app.add_handler(CommandHandler("memory", self._cmd_memory))
        app.add_handler(CommandHandler("strategies", self._cmd_strategies))
        app.add_handler(CommandHandler("risk_deep",  self._cmd_risk_deep))
        app.add_handler(CommandHandler("approvals",  self._cmd_approvals))
        app.add_handler(CommandHandler("trailing",   self._cmd_trailing))
        app.add_handler(CommandHandler("reconcile",  self._cmd_reconcile))
        app.add_handler(CommandHandler("fedwatch",   self._cmd_fedwatch))
        app.add_handler(CommandHandler("yields",     self._cmd_yields))
        app.add_handler(CommandHandler("fear_greed", self._cmd_fear_greed))
        app.add_handler(CommandHandler("cot",        self._cmd_cot))
        app.add_handler(CommandHandler("playbooks",   self._cmd_playbooks))
        app.add_handler(CommandHandler("rollback",    self._cmd_rollback))
        app.add_handler(CommandHandler("crystallized", self._cmd_crystallized))
        # Model override commands → routed to chat with prefix intact
        for cmd in ("fast", "quick", "medium", "mid", "analyze", "analisis", "research"):
            app.add_handler(CommandHandler(cmd, self._handle_chat))
        # Callback queries (inline keyboards)
        app.add_handler(CallbackQueryHandler(self._handle_callback))
        # Free-text → AI chat
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._handle_chat
        ))
        # Voice memo & audio transcription
        if hasattr(self, "voice_handler") and self.voice_handler:
            app.add_handler(MessageHandler(
                filters.VOICE | filters.AUDIO, self.voice_handler.handle_voice
            ))

    async def start(self) -> None:
        """Memulai polling Telegram (blocking)."""
        if not self._app:
            logger.warning("Telegram bot not started — token missing.")
            while True:
                await asyncio.sleep(3600)

        try:
            logger.info("Starting Telegram Bot (polling)...")
            await self._app.initialize()
            await self._app.start()
            if self._app.updater:
                await self._app.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=False,
                )
            self._is_running = True
            logger.info(f"Telegram Bot online. Admin: {self.admin_chat_id}")
            
            # Block until cancelled
            await asyncio.get_running_loop().create_future()
        except asyncio.CancelledError:
            logger.info("Stopping Telegram Bot...")
        finally:
            self._is_running = False
            if self._app:
                try:
                    updater = getattr(self._app, "updater", None)
                    if updater and getattr(updater, "running", False):
                        await updater.stop()
                    if getattr(self._app, "running", False):
                        await self._app.stop()
                    await self._app.shutdown()
                except Exception as e:
                    logger.debug(f"Telegram bot shutdown cleanup: {e}")

    async def stop(self) -> None:
        """Stop the telegram bot application cleanly."""
        self._is_running = False
        if self._app:
            try:
                updater = getattr(self._app, "updater", None)
                if updater and getattr(updater, "running", False):
                    await updater.stop()
                if getattr(self._app, "running", False):
                    await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.debug(f"Telegram bot stop cleanup: {e}")

    async def send_notification(
        self,
        text: str,
        parse_mode: str = ParseMode.HTML,
        message_thread_id: Optional[int] = None,
    ) -> None:
        """Mengirim pesan notifikasi ke admin (digunakan scheduler/risk gate)."""
        if not self._app or not self.admin_chat_id or not self._is_running:
            return

        is_html = (parse_mode == ParseMode.HTML)
        chunks = self._chunk_text(text, max_len=4000, sanitize_format=False, is_html=is_html)

        for chunk in chunks:
            if not self._is_running:
                return
            extra_kwargs = {}
            if message_thread_id is not None:
                extra_kwargs["message_thread_id"] = message_thread_id
            try:
                formatted_chunk = sanitize_telegram_html(chunk) if parse_mode == ParseMode.HTML else chunk
                await self._app.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=formatted_chunk,
                    parse_mode=parse_mode,
                    **extra_kwargs,
                )
            except RuntimeError as r_err:
                logger.debug(f"Telegram notification suppressed (client uninitialized or shutting down): {r_err}")
                return
            except Exception as e:
                # H-4: Fallback to plain text on Markdown formatting failure
                logger.warning(f"Notification send failed with {parse_mode} ({e}), retrying as plain text...")
                try:
                    await self._app.bot.send_message(
                        chat_id=self.admin_chat_id,
                        text=chunk,
                        parse_mode=None,
                        **extra_kwargs,
                    )
                except RuntimeError as r_err:
                    logger.debug(f"Telegram plain text retry suppressed (client shutting down): {r_err}")
                    return
                except Exception as retry_err:
                    logger.error(f"Notification plain text retry failed: {retry_err}")

    async def request_fallback_consent(self, prompt_text: str, tg_event: asyncio.Event, tg_result: dict) -> None:
        """Mengirim notifikasi inline keyboard untuk fallback consent ke admin."""
        if not self._app or not self.admin_chat_id:
            return
            
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        import uuid
        fallback_id = str(uuid.uuid4())[:8]
        
        # Simpan state untuk di-resolve oleh _handle_callback
        if not hasattr(self, '_fallback_events'):
            self._fallback_events = {}
            self._fallback_results = {}
            
        self._fallback_events[fallback_id] = tg_event
        self._fallback_results[fallback_id] = tg_result
        
        keyboard = [
            [InlineKeyboardButton("[ SATU SIKLUS ]", callback_data=f"fallback:once:{fallback_id}")],
            [InlineKeyboardButton("[ SETERUSNYA ]", callback_data=f"fallback:always:{fallback_id}")],
            [InlineKeyboardButton("[ TOLAK ]", callback_data=f"fallback:reject:{fallback_id}")]
        ]
        
        try:
            await self._app.bot.send_message(
                chat_id=self.admin_chat_id,
                text=f"[ PERINGATAN: FALLBACK DIPERLUKAN ]\n\n{prompt_text}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Fallback consent prompt failed: {e}")

    # ------------------------------------------------------------------
    # Auth guard
    # ------------------------------------------------------------------

    def _is_authorized(self, update: Update) -> bool:
        if not update.effective_user:
            return False
        return self._router.is_authorized(update.effective_user.id)

    def _is_admin(self, update: Update) -> bool:
        if not update.effective_user:
            return False
        return self._router.is_admin(update.effective_user.id)

    async def _reject_unauthorized(self, update: Update) -> None:
        # Silent drop — don't reveal bot existence to unauthorized users
        user_id = update.effective_user.id if update.effective_user else "unknown"
        logger.warning(f"Unauthorized: user_id={user_id}")

    async def _reject_non_admin(self, update: Update) -> None:
        if update.message:
            await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        elif update.effective_message:
            await update.effective_message.reply_text("⛔ Perintah ini hanya untuk admin.")

    # ------------------------------------------------------------------
    # Direct command handlers
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        name = (update.effective_user.first_name if update.effective_user else None) or "Trader"
        await update.message.reply_text(
            f"👋 Halo *{name}*!\n\n"
            f"Halo! Saya *Monika* — MT5 Trading Agent otonom berbasis multi-agent LLM.\n\n"
            f"Gunakan /help untuk melihat semua perintah yang tersedia.\n"
            f"Atau ketik pertanyaan apa saja untuk berdiskusi langsung dengan asisten AI.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        from telegram_bot.command_router import CommandRouter
        await update.message.reply_text(
            CommandRouter.build_help_text(),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_interrupt(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
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
                await update.message.reply_text(f"🛑 Analysis interrupted. Note: {redirect_msg}")
            else:
                await update.message.reply_text("ℹ️ No active task currently executing for your session.")
        else:
            await update.message.reply_text("ℹ️ No active chat session found.")

    async def _cmd_resume_proposals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
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
            await update.message.reply_text(f"✅ {res}")
        else:
            await update.message.reply_text("ℹ️ No active chat session found.")

    async def _cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_stats_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _build_stats_text(self) -> str:
        try:
            from database.db import get_session
            from utils.analytics.paper_tracker import PaperTracker
            from telegram_bot.vintage_formatter import format_stats_slip
            
            async with get_session() as session:
                tracker = PaperTracker()
                stats = await tracker.get_statistics(session)
                equity_curve = await tracker.simulate_equity_curve(session)
            
            return format_stats_slip(stats, equity_curve=equity_curve)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _cmd_cost(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        
        try:
            from database.db import get_session
            from utils.analytics.cost_tracker import CostTracker
            async with get_session() as session:
                b_stat = await CostTracker.check_and_update_budget_status(session, self.settings)
                rolling = await CostTracker.get_rolling_7day_cost(session)
                budget = b_stat["monthly_budget"]
                daily_budget = b_stat["daily_budget"]
            
            text = (
                f"💰 *API Cost Report*\n\n"
                f"• *Today Spend:* `${b_stat['daily_cost']:.4f}` / `${daily_budget:.2f}`\n"
                f"• *Month-to-Date:* `${b_stat['mtd_cost']:.4f}` / `${budget:.2f}` ({b_stat['usage_pct']:.1f}%)\n"
                f"• *Last 7 days:* `${rolling['cost_7d']:.4f}` ({rolling['cycles_7d']} cycles)\n"
                f"• *Avg/cycle:* `${rolling['avg_per_cycle']:.4f}`\n"
                f"• *Projected/month:* `${rolling['projected_monthly']:.2f}`\n"
                f"• *Budget Status:* `{'🛑 PAUSED' if b_stat['is_paused'] else '✅ ACTIVE'}`\n"
            )
            if rolling['projected_monthly'] > budget:
                text += f"\n⚠️ *OVER BUDGET projection!* Consider reducing cycles or disabling escalation."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_credits(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_credits_text()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_calibration(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        
        try:
            from database.db import get_session
            from database.models import SystemConfig
            from sqlalchemy import select
            import json as _json
            from utils.analytics.agent_performance_monitor import get_currency_confidence_ceiling
            
            async with get_session() as session:
                cal_cfg = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == "news_tier_calibration_directives")
                )).scalar_one_or_none()
                
                lines = [f"⚙️ *System Calibration States*"]
                if cal_cfg and cal_cfg.value:
                    cal_data = _json.loads(cal_cfg.value)
                    if cal_data:
                        lines.append("\n📰 *News Directives:*")
                        for k, v in cal_data.items():
                            lines.append(f"• `{k}`: {v}")
                        
                ceilings = await get_currency_confidence_ceiling(session, days_back=30)
                if ceilings:
                    lines.append("\n🎯 *Confidence Ceilings:*")
                    for cur, cap in ceilings.items():
                        lines.append(f"• `{cur}`: Max {cap}")
                
                from utils.protocol.enhanced_cds import get_cds_thresholds_async
                cds_thr = await get_cds_thresholds_async(session, self.settings)
                lines.append('\n📐 *SSVP CDS Thresholds:*')
                for k, v in cds_thr.items():
                    lines.append(f'• `{k}`: {v}')
                
                from utils.analytics.specialist_tracker import compute_specialist_reliability
                spec_rel = await compute_specialist_reliability(session)
                if spec_rel.get('specialists'):
                    lines.append('\n🧑‍💼 *Specialist Trust Weights:*')
                    for name, d in spec_rel['specialists'].items():
                        flag = ' ⚠️ CHRONIC' if d.get('chronically_unreliable') else ''
                        lines.append(f"• `{name}`: {d['trust_weight']} (acc={d['accuracy_pct']}%, n={d['total']}){flag}")
                
                infl_cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'score_inflation_correction_threshold'))).scalar_one_or_none()
                if infl_cfg and infl_cfg.value:
                    infl_data = _json.loads(infl_cfg.value)
                    lines.append(f"\n📊 *Score Inflation Correction:* threshold={infl_data.get('threshold')} (set {infl_data.get('set_at','')[:10]})")
            
            text = "\n".join(lines) if len(lines) > 1 else "No active calibration directives."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_edge(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        from utils.analytics.analysis_tracker import get_direction_accuracy_report, compute_factor_effectiveness
        from utils.analytics.paper_tracker import PaperTracker
        from database.db import get_session
        
        await update.message.reply_text("⏳ Menghitung edge assessment... (bisa memakan waktu beberapa detik)")
        
        async with get_session() as session:
            dir_acc = await get_direction_accuracy_report(session, 14)
            factors = await compute_factor_effectiveness(session, 30)
            tracker = PaperTracker()
            stats = await tracker.get_statistics(session)
            
        msg = "📊 *EDGE ASSESSMENT*\n\n"
        msg += f"• *Win Rate (Paper):* {stats.get('win_rate_pct', 0)}% (Total: {stats.get('total_trades', 0)})\n"
        if not dir_acc.get('insufficient_data') and 'overall_accuracy_4h_pct' in dir_acc:
            msg += f"• *Direction Accuracy (4H):* {dir_acc['overall_accuracy_4h_pct']}%\n\n"
        elif 'direction_accuracy_4h' in dir_acc and dir_acc['direction_accuracy_4h'] is not None:
            msg += f"• *Direction Accuracy (4H):* {dir_acc['direction_accuracy_4h']}%\n\n"
            
        msg += "*Top Edge Factors:*\n"
        raw_factors = factors.get("factor_effectiveness", {}) if isinstance(factors, dict) else {}
        top_factors = sorted(raw_factors.items(), key=lambda x: x[1].get('win_rate', 0) if isinstance(x[1], dict) else 0, reverse=True)[:5]
        if top_factors:
            for factor, data in top_factors:
                if isinstance(data, dict):
                    msg += f"- {factor.upper()}: {data.get('win_rate', 0)}% WR ({data.get('wins', 0)}/{data.get('total', 0)})\n"
        else:
            msg += "- _Insufficient data for factor edge calculation_\n"
            
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_status_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_positions(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_positions_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_brief(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_brief_text()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_analysis(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        
        if not ctx.args:
            await update.message.reply_text("Usage: /analysis <symbol>")
            return
            
        symbol = ctx.args[0].upper()
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_analysis_text(symbol)
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_history_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_risk(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        text = await self._build_risk_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_risk_deep(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_risk_deep_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_approvals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_approvals_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_trailing(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_trailing_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_reconcile(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_reconcile_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_fedwatch(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_fedwatch_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_yields(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_yields_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_fear_greed(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_fear_greed_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_cot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        market_code = ctx.args[0] if ctx.args else None
        text = await self._build_cot_text(market_code)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_playbooks(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_playbooks_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_rollback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        if not ctx.args:
            await update.message.reply_text("Format: `/rollback <playbook_name>`\nContoh: `/rollback eurusd_trend`", parse_mode=ParseMode.MARKDOWN)
            return
        name = ctx.args[0].strip()
        text = await self._build_rollback_text(name)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_crystallized(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_crystallized_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_vix(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        text = await self._build_vix_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_tokens(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_tokens_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_intel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        
        from database.db import get_session
        from database.models import UserMarketIntel
        from sqlalchemy import select, or_
        import utils.clock as clock

        now = clock.now()
        async with get_session() as session:
            stmt = (
                select(UserMarketIntel)
                .where(
                    UserMarketIntel.is_active == True,
                    or_(UserMarketIntel.expires_at.is_(None), UserMarketIntel.expires_at > now),
                )
                .order_by(UserMarketIntel.created_at.desc())
            )
            records = (await session.execute(stmt)).scalars().all()

        if not records:
            await update.message.reply_text(
                "ℹ️ *Tidak ada Market Intelligence aktif.*\nGunakan /research atau chat untuk melakukan riset dan menyimpan intel baru.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        lines = [f"🧠 *MARKET INTELLIGENCE AKTIF ({len(records)})*\n"]
        for r in records:
            symbols = ", ".join(r.affected_symbols_list) if hasattr(r, "affected_symbols_list") else (r.affected_symbols or "ALL")
            directive_str = f" | Directive: *{r.directive.upper()}*" if r.directive else ""
            target_cycle = f" | Target: {r.target_cycle}" if r.target_cycle else ""
            exp_str = r.expires_at.strftime("%Y-%m-%d %H:%M") if r.expires_at else "No expiry"
            
            lines.append(
                f"• *#{r.id}* [{r.intel_type.upper()}] *{r.title}*\n"
                f"  Aset: `{symbols}`{directive_str}{target_cycle}\n"
                f"  Exp: {exp_str}\n"
                f"  _{r.summary}_\n"
            )
        lines.append("_Gunakan `/archive_intel <id>` untuk menonaktifkan intel._")
        text = "\n".join(lines)
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_archive_intel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_non_admin(update)
        
        if not ctx.args or not ctx.args[0].strip().isdigit():
            await update.message.reply_text("Format: `/archive_intel <intel_id>`\nContoh: `/archive_intel 1`", parse_mode=ParseMode.MARKDOWN)
            return

        intel_id = int(ctx.args[0].strip())
        from database.db import get_session
        from database.models import UserMarketIntel, ActivityLog
        from sqlalchemy import select

        async with get_session() as session:
            stmt = select(UserMarketIntel).where(UserMarketIntel.id == intel_id)
            intel = (await session.execute(stmt)).scalar_one_or_none()
            if not intel:
                await update.message.reply_text(f"❌ Market Intelligence #{intel_id} tidak ditemukan.")
                return
            if not intel.is_active:
                await update.message.reply_text(f"ℹ️ Market Intelligence #{intel_id} sudah tidak aktif.")
                return

            intel.is_active = False
            user_id_str = str(update.effective_user.id) if update.effective_user else "unknown"
            session.add(ActivityLog(
                category="intel",
                description=f"Market Intelligence #{intel_id} deactivated via /archive_intel by user {user_id_str}",
                actor="telegram_bot",
            ))
            await session.commit()

        await update.message.reply_text(f"✅ Market Intelligence *#{intel_id}* berhasil dinonaktifkan.", parse_mode=ParseMode.MARKDOWN)

    # Admin commands

    async def _cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)
        clean_args = [a for a in ctx.args if a not in ("-y", "--force")] if ctx.args else []
        reason = " ".join(clean_args) if clean_args else "Paused via Telegram"

        if not ctx.args or ("-y" not in ctx.args and "--force" not in ctx.args):
            import secrets, time
            nonce = secrets.token_hex(4)
            if not hasattr(self, '_active_nonces'):
                self._active_nonces = {}
            self._active_nonces[nonce] = {"action": "pause", "reason": reason, "expires": time.time() + 120.0}

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("[ KONFIRMASI JEDA ]", callback_data=f"pause:confirm:{nonce}"),
                InlineKeyboardButton("[ BATAL ]", callback_data="cancel"),
            ]])
            await update.message.reply_text(
                f"[ PERINGATAN: KONFIRMASI JEDA TRADING ]\n\n"
                f"Alasan: {reason}\n"
                f"Apakah Anda yakin ingin menjeda seluruh eksekusi trading?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            return

        from database.db import get_session
        from risk.risk_gate import RiskGate
        gate = RiskGate(self.settings)
        async with get_session() as session:
            await gate.pause_trading(session, reason)
        await update.message.reply_text(f"[ PAUSED ] Trading dijeda.\nAlasan: {reason}", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)
        from database.db import get_session
        from risk.risk_gate import RiskGate
        from utils.analytics.cost_tracker import CostTracker
        gate = RiskGate(self.settings)
        async with get_session() as session:
            await gate.resume_trading(session)
            await CostTracker.clear_budget_pause(session)
        await update.message.reply_text("[ RESUMED ] Trading & AI Budget dilanjutkan.", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_unsuspend(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text("Penggunaan: `/unsuspend <symbol>` atau `/unsuspend all`", parse_mode=ParseMode.MARKDOWN)
            return

        target = ctx.args[0].strip().upper()
        from database.db import get_session
        from utils.analytics.paper_tracker import PaperTracker

        tracker = PaperTracker(self.settings)
        async with get_session() as session:
            if target == "ALL":
                cleared = await tracker.unsuspend_all(session)
                if cleared:
                    await update.message.reply_text(f"[ OK ] Berhasil membuka blokir semua simbol: `{', '.join(cleared)}`", parse_mode=ParseMode.MARKDOWN)
                else:
                    await update.message.reply_text("[ INFO ] Tidak ada simbol yang sedang tersuspensi.", parse_mode=ParseMode.MARKDOWN)
            else:
                ok = await tracker.unsuspend_symbol(session, target)
                if ok:
                    await update.message.reply_text(f"[ OK ] Berhasil membuka blokir simbol *{target}*.", parse_mode=ParseMode.MARKDOWN)
                else:
                    await update.message.reply_text(f"[ INFO ] Simbol *{target}* tidak ditemukan dalam daftar suspensi.", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_kill(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        import secrets, time
        nonce = secrets.token_hex(4)
        if not hasattr(self, '_active_nonces'):
            self._active_nonces = {}
        self._active_nonces[nonce] = {"action": "killswitch", "expires": time.time() + 120.0}

        # Two-step confirm for kill switch with single-use nonce
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("[ KONFIRMASI TUTUP SEMUA ]", callback_data=f"killswitch:confirm:{nonce}"),
            InlineKeyboardButton("[ BATAL ]",            callback_data="cancel"),
        ]])
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
        await update.message.reply_text('🚨 EMERGENCY CLOSE INITIATED - NO CONFIRMATION NEEDED')
        if self.execution_service:
            result = await self.execution_service.kill_switch('EMERGENCY TELEGRAM COMMAND - INSTANT')
            await update.message.reply_text(
                f"💥 Emergency close done: {result['closed']}/{result['total']} positions closed"
            )
        else:
            await update.message.reply_text("⚠️ ExecutionService tidak terhubung.")

    async def _cmd_close(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text("Usage: /close <ticket>")
            return

        try:
            ticket = int(ctx.args[0])
        except ValueError:
            await update.message.reply_text("❌ Ticket harus berupa angka.")
            return

        from telegram_bot.command_router import CommandRouter
        keyboard = CommandRouter.build_close_keyboard(ticket)
        await update.message.reply_text(
            f"⚠️ Konfirmasi tutup posisi *#{ticket}*?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    async def _cmd_closeall(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Tutup semua posisi aktif (Admin only)."""
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not self.execution_service:
            await update.message.reply_text("⚠️ ExecutionService tidak terhubung.")
            return

        await update.message.reply_text("🚨 Memproses penutupan seluruh posisi terbuka...")
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
                f"✅ *Close All Selesai*: {closed}/{total} posisi berhasil ditutup.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal menutup semua posisi: {e}")

    async def _cmd_override(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Ubah parameter risiko secara dinamis (Admin only)."""
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args or len(ctx.args) < 2:
            help_text = (
                "⚙️ *Penggunaan /override:*\n"
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
                await update.message.reply_text(f"❌ Nilai tidak valid untuk `{param}`: {val_str}")
                return
        else:
            await update.message.reply_text(f"❌ Parameter `{param}` tidak dikenali. Ketik `/override` untuk opsi.")
            return

        from database.db import get_session
        from database.models import SystemConfig, ActivityLog
        from sqlalchemy import select
        import json

        async with get_session() as session:
            cfg_row = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == "risk_override")
            )).scalar_one_or_none()

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

            session.add(ActivityLog(
                category="risk",
                description=f"Risk override via Telegram: {updated_fields if param != 'reset' else 'RESET'}",
                actor="telegram_admin",
            ))
            await session.commit()

        if hasattr(self, "settings") and isinstance(self.settings, dict):
            trading_risk = self.settings.setdefault("trading", {}).setdefault("risk", {})
            trading_risk.update(current_cfg)

        try:
            from logging_observability.dashboard.routes.common import broadcast_live_event
            await broadcast_live_event("risk_override_updated", {
                "updated_fields": current_cfg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ *Risk Override Diterapkan:*\n`{json.dumps(current_cfg, indent=2)}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_regime(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Deteksi rezim makro dan volatilitas terkini."""
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        symbol = ctx.args[0].upper().strip() if ctx.args else "XAUUSD"
        await update.message.reply_text(f"🔍 Menganalisis rezim pasar untuk *{symbol}*...", parse_mode=ParseMode.MARKDOWN)

        from database.db import get_session
        from database.models import FundamentalBrief, VIXData
        from analysis.calculators.regime_classifier import classify_market_regime
        from sqlalchemy import select, desc

        async with get_session() as session:
            try:
                regime_data = await classify_market_regime(session, symbol, settings=self.settings)
                final_regime = regime_data.get("regime", "UNKNOWN")
                quality = regime_data.get("composite_quality", 0.0)
                adx = regime_data.get("adx")
                vol_ratio = regime_data.get("vol_ratio")
            except Exception as e:
                final_regime = f"Calculated ({e})"
                quality = 0.0
                adx = None
                vol_ratio = None

            vix_row = (await session.execute(
                select(VIXData).order_by(desc(VIXData.date)).limit(1)
            )).scalar_one_or_none()
            vix_val = vix_row.close if vix_row else 15.0

            brief_row = (await session.execute(
                select(FundamentalBrief).order_by(desc(FundamentalBrief.generated_at)).limit(1)
            )).scalar_one_or_none()
            macro_sentiment = brief_row.risk_sentiment if brief_row else "neutral"

        lines = [
            f"📊 *Rezim Pasar & Volatilitas* — `{symbol}`",
            f"• *Rezim Komposit:* `{final_regime}`",
            f"• *Kualitas Sinyal:* `{quality:.2f}`",
            f"• *ADX Trend Strength:* `{adx if adx is not None else 'N/A'}`",
            f"• *Rasio Ekspansi Volatilitas:* `{vol_ratio:.2f}`" if vol_ratio else "• *Rasio Volatilitas:* `N/A`",
            f"• *VIX Indeks:* `{vix_val:.2f}`",
            f"• *Sentimen Makro Global:* `{macro_sentiment.upper()}`",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_audit(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Jejak audit penalaran trade dan event lifecycle."""
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        from database.db import get_session
        from database.models import Position, AssetAnalysis
        from sqlalchemy import select, desc

        ticket_arg = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else None

        async with get_session() as session:
            if ticket_arg:
                pos = (await session.execute(
                    select(Position).where(Position.mt5_ticket == ticket_arg)
                )).scalar_one_or_none()

                if not pos:
                    await update.message.reply_text(f"❌ Posisi dengan ticket *#{ticket_arg}* tidak ditemukan.")
                    return

                analysis = None
                if pos.analysis_id:
                    analysis = await session.get(AssetAnalysis, pos.analysis_id)

                lines = [
                    f"📜 *Audit Trail — Ticket #{ticket_arg}*",
                    f"• Simbol: `{pos.symbol}` | Side: `{pos.direction}` | Lot: `{pos.volume}`",
                    f"• Entry: `{pos.entry_price}` | SL: `{pos.sl}` | TP: `{pos.tp}`",
                    f"• Status: `{pos.status}` | PnL: `${pos.pnl:,.2f}`" if pos.pnl is not None else f"• Status: `{pos.status}`",
                    f"• Waktu Buka: `{pos.opened_at.strftime('%Y-%m-%d %H:%M:%S UTC')}`" if pos.opened_at else "",
                ]
                if analysis:
                    lines.extend([
                        f"\n🧠 *AI Reasoning:*",
                        f"• Confluence Score: `{analysis.confluence_score}`",
                        f"• Confidence: `{analysis.confidence:.0%}`",
                        f"• Regime: `{analysis.market_regime_at_analysis or 'N/A'}`",
                        f"• Rasional: _{analysis.rationale[:250]}..._" if analysis.rationale else "",
                    ])
                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
            else:
                positions = (await session.execute(
                    select(Position).order_by(desc(Position.opened_at)).limit(5)
                )).scalars().all()

                if not positions:
                    await update.message.reply_text("ℹ️ Belum ada riwayat posisi untuk diaudit.")
                    return

                lines = ["📜 *Audit 5 Posisi Terakhir:*"]
                for p in positions:
                    pnl_str = f"+${p.pnl:,.2f}" if p.pnl and p.pnl >= 0 else f"-${abs(p.pnl or 0):,.2f}"
                    lines.append(f"• `#{p.mt5_ticket or p.id}` {p.symbol} {p.direction} {p.volume}L — {p.status} ({pnl_str})")
                lines.append("\nKetik `/audit <ticket>` untuk detail lengkap satu posisi.")
                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_run(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        await update.message.reply_text("🔄 Menjalankan siklus analisis manual...")
        if self.cycle_scheduler:
            asyncio.create_task(self._run_cycle_and_notify(update))
        else:
            await update.message.reply_text("⚠️ Scheduler tidak terhubung.")

    async def _run_cycle_and_notify(self, update: Update) -> None:
        if not self.cycle_scheduler or not update.message:
            return
        try:
            summary = await self.cycle_scheduler.run_once(forced=True)
            pa = summary.get("per_asset", {})
            lines = [f"✅ *Siklus analisis selesai*"]
            for sym, r in pa.items():
                decision = (r.get("decision") or "N/A").upper()
                conf     = r.get("confidence") or 0
                lines.append(f"  {sym}: `{decision}` ({conf:.0%})")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"❌ Siklus gagal: {e}")

    async def _cmd_backtest(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        days = 30
        mode = "full"
        equity = 10000.0

        if ctx.args:
            try:
                days = int(ctx.args[0])
                if days <= 0 or days > 365:
                    await update.message.reply_text("❌ Parameter hari harus antara 1 dan 365.")
                    return
            except ValueError:
                await update.message.reply_text("❌ Format salah. Contoh: `/backtest 30 [mode] [equity]`", parse_mode=ParseMode.MARKDOWN)
                return

            if len(ctx.args) > 1:
                arg_mode = ctx.args[1].lower()
                if arg_mode in ("full", "replay", "walk_forward", "langgraph_parity"):
                    mode = arg_mode

            if len(ctx.args) > 2:
                try:
                    equity = float(ctx.args[2])
                except ValueError:
                    pass

        await update.message.reply_text(
            f"⏳ *Memulai Point-in-Time Backtest ({days} hari)...*\n\n"
            f"Proses berjalan di background. Anda akan menerima notifikasi ringkasan setelah selesai.",
            parse_mode=ParseMode.MARKDOWN,
        )
        if mode == "full" and equity == 10000.0:
            asyncio.create_task(self._run_backtest_and_notify(update, days))
        else:
            asyncio.create_task(self._run_backtest_and_notify(update, days, mode=mode, initial_equity=equity))

    async def _run_backtest_and_notify(
        self, update: Update, days: int, mode: str = "full", initial_equity: float = 10000.0
    ) -> None:
        if not update.message:
            return
        try:
            from backtest.point_in_time_engine import PointInTimeBacktestEngine
            from backtest.walk_forward_engine import WalkForwardEngine
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            if mode == "walk_forward":
                engine = WalkForwardEngine(
                    start_date=start_time,
                    end_date=end_time,
                    settings=self.settings,
                    mode="full",
                )
                result = await engine.run()
                msg = (
                    f"✅ <b>Walk-Forward Optimization Selesai!</b>\n\n"
                    f"Overall WFE: <b>{result.overall_wfe:.2f}</b>\n"
                    f"IS Sharpe: {result.aggregate_is_sharpe:.2f}\n"
                    f"OOS Sharpe: {result.aggregate_oos_sharpe:.2f}\n"
                    f"OOS Trades: {result.total_oos_trades}\n"
                    f"Overfit: {'⚠️ YES' if result.is_overfit else '✅ NO'}\n"
                )
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
                return

            engine = PointInTimeBacktestEngine(
                start_time, end_time, self.settings, mode=mode, initial_equity=initial_equity
            )
            run_record = await engine.run()
            
            # Calculate by_symbol aggregation manually
            by_symbol = {}
            for t in engine.trades:
                sym = t.symbol
                if sym not in by_symbol:
                    by_symbol[sym] = {'trades': 0, 'wins': 0, 'total_pnl': 0.0}
                by_symbol[sym]['trades'] += 1
                if (t.pnl_pct or 0) > 0:
                    by_symbol[sym]['wins'] += 1
                by_symbol[sym]['total_pnl'] += (t.pnl_pct or 0)
                
            for sym, data in by_symbol.items():
                data['win_rate'] = round((data['wins'] / data['trades']) * 100, 2)
                
            total_pnl_pct = 0.0
            if run_record.initial_equity and run_record.final_equity is not None and run_record.initial_equity > 0:
                total_pnl_pct = ((run_record.final_equity - run_record.initial_equity) / run_record.initial_equity) * 100

            msg = (
                f"✅ <b>Backtest {days} hari Selesai!</b>\n\n"
                f"<b>📊 PERFORMANCE REPORT:</b>\n"
                f"Total trades: {run_record.total_trades}\n"
                f"Win rate: {float(run_record.win_rate):.2f}%\n"
            )
            if hasattr(run_record, "profit_factor") and isinstance(run_record.profit_factor, (int, float)):
                msg += f"Profit Factor: {run_record.profit_factor:.2f}\n"
            if hasattr(run_record, "sharpe_ratio") and isinstance(run_record.sharpe_ratio, (int, float)):
                msg += f"Sharpe (Ann): {run_record.sharpe_ratio:.2f}\n"
            if hasattr(run_record, "max_drawdown_pct") and isinstance(run_record.max_drawdown_pct, (int, float)):
                msg += f"Max Drawdown: {run_record.max_drawdown_pct:.2f}%\n"
            msg += f"Total PnL: {total_pnl_pct:+.2f}%\n\n"
            msg += "<b>By Symbol:</b>\n"
            for sym, data in by_symbol.items():
                msg += f"• {sym}: {data['trades']} trades, {data['win_rate']}% WR, {data['total_pnl']:+.2f}% PnL\n"
                
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Backtest gagal: {e}")

    async def _cmd_calendar(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        from database.db import AsyncSessionLocal
        from database.models import EconomicCalendar
        from sqlalchemy import select

        currency = ctx.args[0].upper() if ctx.args else None
        now = datetime.now(timezone.utc)
        until = now + timedelta(hours=36)

        try:
            async with AsyncSessionLocal() as session:
                q = select(EconomicCalendar).where(
                    EconomicCalendar.event_time >= now - timedelta(hours=2),
                    EconomicCalendar.event_time <= until
                )
                if currency:
                    q = q.where(EconomicCalendar.currency.contains(currency))
                q = q.order_by(EconomicCalendar.event_time.asc()).limit(15)
                events = (await session.execute(q)).scalars().all()

                if not events:
                    filter_txt = f" untuk {currency}" if currency else ""
                    await update.message.reply_text(f"ℹ️ Tidak ada event kalender signifikan dalam 36 jam ke depan{filter_txt}.")
                    return

                lines = ["📅 <b>Jadwal Kalender Ekonomi Makro (Next 36h):</b>\n"]
                for e in events:
                    impact_emoji = "🔴" if (e.impact or "").lower() == "high" else "🟡" if (e.impact or "").lower() == "medium" else "⚪"
                    t_str = e.event_time.strftime("%d %b %H:%M UTC") if e.event_time else "TBD"
                    act = f" | Act: {e.actual}" if e.actual else ""
                    fcst = f" | Fct: {e.forecast}" if e.forecast else ""
                    lines.append(f"{impact_emoji} <b>[{e.currency}]</b> {e.event_name}\n   ⏰ <code>{t_str}</code>{fcst}{act}")

                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error fetching calendar: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Gagal memuat kalender ekonomi: {e}")

    async def _cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        try:
            from skills.loader import list_skills
            all_s = list_skills()
            playbooks = [s for s in all_s if "playbook" in s.lower() or s.startswith("alpha_")]
            core = [s for s in all_s if s not in playbooks]

            lines = [
                f"🧠 <b>Autonomous Skills & Playbooks ({len(all_s)} Total)</b>\n",
                f"<b>Core Prompt Skills ({len(core)}):</b>",
            ]
            for s in core[:8]:
                lines.append(f"• <code>{s}</code>")
            if len(core) > 8:
                lines.append(f"<i>...dan {len(core)-8} lainnya</i>")

            lines.append(f"\n<b>Playbook Strategies ({len(playbooks)}):</b>")
            for p in playbooks[:8]:
                lines.append(f"• <code>{p}</code>")
            if len(playbooks) > 8:
                lines.append(f"<i>...dan {len(playbooks)-8} lainnya</i>")

            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error listing skills: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Gagal memuat daftar skills: {e}")

    def _build_plugins_text(self, plugins: list[dict]) -> str:
        active_count = sum(1 for p in plugins if p.get("enabled", False))
        lines = [
            f"🔌 <b>MONIKA PLUG-IN HARNESS ({active_count}/{len(plugins)} AKTIF)</b>",
            "<i>Ketuk tombol di bawah untuk toggle ON/OFF secara instan:</i>\n",
        ]
        for p in plugins:
            icon = "🟢" if p.get("enabled") else "⚪"
            status = "ACTIVE" if p.get("enabled") else ("DEGRADED" if str(p.get("status", "")).startswith("DEGRADED") else "DISABLED")
            cat = p.get("category", "custom")
            lines.append(f"{icon} <b>{p.get('name', p['id'])}</b> <code>v{p.get('version', '1.0')}</code> [{cat}]")
            lines.append(f"   <i>Status: {status}</i> • <code>{p['id']}</code>")
        return "\n".join(lines)

    def _build_plugins_keyboard(self, plugins: list[dict]) -> InlineKeyboardMarkup:
        keyboard = []
        row = []
        for p in plugins:
            btn_icon = "🟢" if p.get("enabled") else "⚪"
            btn_label = f"{btn_icon} {p.get('name', p['id'])[:15]}"
            cb_data = f"plg:t:{p['id'][:32]}"
            row.append(InlineKeyboardButton(btn_label, callback_data=cb_data))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([
            InlineKeyboardButton("📦 Marketplace Catalog", callback_data="plg:cat"),
            InlineKeyboardButton("🔄 Refresh", callback_data="plg:ref"),
        ])
        return InlineKeyboardMarkup(keyboard)

    async def _cmd_plugins(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        try:
            from harness.installer import list_all_plugins_status
            plugins = list_all_plugins_status()
            if not plugins:
                await update.message.reply_text("ℹ️ Belum ada modul plugin yang terdaftar di sistem.")
                return

            text = self._build_plugins_text(plugins)
            markup = self._build_plugins_keyboard(plugins)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error listing plugins in Telegram: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Gagal memuat status plugins: {e}")

    async def _cmd_plugin_catalog(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        try:
            from harness.installer import get_community_catalog
            catalog = get_community_catalog()
            lines = ["📦 <b>KATALOG MARKETPLACE PLUG-IN MONIKA</b>\n"]
            kb = []
            for item in catalog:
                lines.append(f"• <b>{item['name']}</b> (<code>{item['package']}</code>)\n  <i>{item['description']}</i>\n")
                kb.append([InlineKeyboardButton(f"📥 Install {item['name'][:20]}", callback_data=f"plg:inst:{item['package'][:30]}")])
            kb.append([InlineKeyboardButton("🔌 Plugins Terpasang", callback_data="plg:ref")])
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            logger.error(f"Error viewing plugin catalog: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Gagal memuat katalog plugin: {e}")

    async def _cmd_plugin_install(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text(
                "ℹ️ Format: <code>/plugin_install &lt;package_name&gt;</code>\nContoh: <code>/plugin_install monika-plugin-deepseek</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        pkg = ctx.args[0].strip()
        from harness.installer import validate_package_spec, run_pip_install
        valid, err = validate_package_spec(pkg)
        if not valid:
            await update.message.reply_text(f"❌ <b>Validasi Paket Ditolak:</b>\n{err}", parse_mode=ParseMode.HTML)
            return

        msg = await update.message.reply_text(f"⏳ <b>Menginstall plugin via pip:</b> <code>{pkg}</code>...\n<i>Mohon tunggu sebentar...</i>", parse_mode=ParseMode.HTML)
        success, out = await asyncio.to_thread(run_pip_install, pkg)
        
        status_icon = "✅" if success else "❌"
        status_word = "Berhasil" if success else "Gagal"
        tail_out = out[-400:] if len(out) > 400 else out
        await msg.edit_text(f"{status_icon} <b>Instalasi {status_word}:</b> <code>{pkg}</code>\n\n<pre>{tail_out}</pre>", parse_mode=ParseMode.HTML)

    async def _cmd_plugin_uninstall(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text("ℹ️ Format: <code>/plugin_uninstall &lt;package_name&gt;</code>", parse_mode=ParseMode.HTML)
            return

        pkg = ctx.args[0].strip()
        from harness.installer import run_pip_uninstall
        msg = await update.message.reply_text(f"⏳ <b>Menghapus paket via pip:</b> <code>{pkg}</code>...", parse_mode=ParseMode.HTML)
        success, out = await asyncio.to_thread(run_pip_uninstall, pkg)
        status_icon = "✅" if success else "❌"
        await msg.edit_text(f"{status_icon} <b>Uninstall {'Berhasil' if success else 'Gagal'}:</b> <code>{pkg}</code>", parse_mode=ParseMode.HTML)

    async def _cmd_plugin_toggle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args:
            await update.message.reply_text("ℹ️ Format: <code>/plugin_toggle &lt;plugin_id&gt;</code>", parse_mode=ParseMode.HTML)
            return

        plugin_id = ctx.args[0].strip()
        from harness.installer import list_all_plugins_status, toggle_plugin_state
        plugins = {p["id"]: p for p in list_all_plugins_status()}
        if plugin_id in plugins:
            p = plugins[plugin_id]
            if not p["can_toggle"]:
                await update.message.reply_text("⚠️ Komponen inti (core) tidak dapat dinonaktifkan.")
                return
            new_state = not p["enabled"]
            ok, res_msg = toggle_plugin_state(plugin_id, p["category"], new_state)
            await update.message.reply_text(f"{'🟢' if new_state else '⚪'} {res_msg}")
        else:
            await update.message.reply_text(f"❌ Plugin '<code>{plugin_id}</code>' tidak ditemukan.", parse_mode=ParseMode.HTML)

    async def _cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        query = " ".join(ctx.args).strip() if ctx.args else ""
        from database.db import AsyncSessionLocal
        from database.models import DecisionReflection
        from sqlalchemy import select, or_

        try:
            async with AsyncSessionLocal() as session:
                if query:
                    q = select(DecisionReflection).where(
                        or_(
                            DecisionReflection.symbol.ilike(f"%{query}%"),
                            DecisionReflection.reflection_text.ilike(f"%{query}%"),
                            DecisionReflection.specific_lesson.ilike(f"%{query}%"),
                        )
                    ).order_by(DecisionReflection.id.desc()).limit(5)
                else:
                    q = select(DecisionReflection).order_by(DecisionReflection.id.desc()).limit(5)

                reflections = (await session.execute(q)).scalars().all()

                if not reflections:
                    await update.message.reply_text("ℹ️ Belum ada rekaman refleksi memori yang cocok.")
                    return

                lines = [f"🏛️ <b>Autonomous Memory Vault ({len(reflections)} Terkini)</b>\n"]
                for r in reflections:
                    res_emoji = "🟢" if (r.outcome_pnl_usd or 0) > 0 else "🔴"
                    pnl_str = f"${r.outcome_pnl_usd:+,.2f}" if r.outcome_pnl_usd is not None else "N/A"
                    lesson_snippet = r.specific_lesson or (r.reflection_text[:120] if r.reflection_text else "No lesson recorded.")
                    lines.append(
                        f"{res_emoji} <b>[{r.symbol}]</b> {r.decision.upper()} | PnL: <code>{pnl_str}</code>\n"
                        f"💡 <i>{lesson_snippet}</i>\n"
                    )

                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error retrieving memory: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Gagal membaca memori: {e}")

    async def _cmd_strategies(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)

        from database.db import AsyncSessionLocal
        from database.models import PlaybookRuleAttribution
        from sqlalchemy import select

        try:
            async with AsyncSessionLocal() as session:
                rules = (
                    await session.execute(
                        select(PlaybookRuleAttribution).order_by(PlaybookRuleAttribution.times_triggered.desc()).limit(10)
                    )
                ).scalars().all()

                if not rules:
                    await update.message.reply_text("ℹ️ Belum ada aturan playbook / strategi empiris terdaftar di DB.")
                    return

                lines = ["⚔️ <b>Empirical Playbook Strategies & Rules:</b>\n"]
                for rule in rules:
                    wr = (rule.win_rate or 0.0) * 100
                    pnl = rule.total_pnl or 0.0
                    rule_snippet = (rule.rule_text[:90] + "...") if len(rule.rule_text) > 90 else rule.rule_text
                    lines.append(
                        f"• <b>[{rule.symbol}]</b> <code>{rule.status.upper()}</code>\n"
                        f"  Rule: <i>{rule_snippet}</i>\n"
                        f"  Triggers: <b>{rule.times_triggered}</b> | WR: <b>{wr:.1f}%</b> | PnL: <code>${pnl:+,.2f}</code>\n"
                    )

                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error retrieving strategies: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Gagal memuat playbook strategies: {e}")

    # ------------------------------------------------------------------
    # AI chat handler
    # ------------------------------------------------------------------

    async def _handle_chat(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return
        if not self._is_authorized(update) or not update.effective_user:
            return await self._reject_unauthorized(update)

        user_id  = update.effective_user.id
        chat_id  = update.effective_chat.id if update.effective_chat else user_id
        user_msg = update.message.text.strip()
        
        # Prune old chat agents
        now = datetime.now(timezone.utc)
        to_delete = []
        for uid, agent in self._chat_agents.items():
            if agent.last_active is not None and (now - agent.last_active).total_seconds() > 3600:
                to_delete.append(uid)
        for uid in to_delete:
            del self._chat_agents[uid]

        # Check if message is from a forum topic thread
        thread_id = getattr(update.message, "message_thread_id", None)
        session_id = None
        if isinstance(thread_id, int) and hasattr(self, "topic_manager") and self.topic_manager:
            session_id = await self.topic_manager.get_session_for_topic(chat_id, thread_id)
            if not session_id:
                session_id = await self.topic_manager.create_topic_session(
                    chat_id, thread_id, topic_name=f"Topic-{thread_id}"
                )
            agent_key = session_id
        else:
            agent_key = user_id

        # Show typing indicator
        if update.message.chat:
            try:
                res = update.message.chat.send_action(ChatAction.TYPING)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        # Get or create per-user / per-topic ChatAgent
        is_admin_user = self._is_admin(update)
        if agent_key not in self._chat_agents:
            from telegram_bot.chat_agent import ChatAgent
            self._chat_agents[agent_key] = ChatAgent(self.settings, agent_key, is_admin=is_admin_user)

        agent = self._chat_agents[agent_key]
        agent.is_admin = is_admin_user
        agent.last_active = now

        chat_obj = update.message.chat
        async def _typing_cb():
            if chat_obj:
                await chat_obj.send_action(ChatAction.TYPING)

        status_msg: Optional[Message] = None
        async def _status_cb(msg_text: str):
            nonlocal status_msg
            if update.message:
                try:
                    if status_msg is None:
                        status_msg = await update.message.reply_text(f"_{msg_text}_", parse_mode=ParseMode.MARKDOWN)
                    else:
                        await status_msg.edit_text(f"_{msg_text}_", parse_mode=ParseMode.MARKDOWN)
                except Exception as _st_err:
                    logger.debug(f"Failed to update status message: {_st_err}")

        is_streaming_enabled = self.settings.get("telegram", {}).get("streaming", False)

        try:
            reply, pending = await agent.handle(
                user_msg,
                context=ctx,
                typing_callback=_typing_cb,
                status_callback=_status_cb,
                session_id=session_id,
                stream=is_streaming_enabled,
                update=update,
            )
        except Exception as e:
            logger.error(f"ChatAgent error for user {user_id}: {e}")
            await update.message.reply_text(f"[ERROR] {e}")
            return
        finally:
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

        # Send reply in chunks (Telegram 4096 char limit) when not already streamed
        if not is_streaming_enabled:
            for chunk in self._chunk_text(reply):
                try:
                    formatted_chunk = sanitize_telegram_html(chunk)
                    await update.message.reply_text(formatted_chunk, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.warning(f"Failed to send HTML reply chunk, falling back to plain text: {e}")
                    await update.message.reply_text(chunk)

        # Send any generated chart images
        if hasattr(agent, 'pop_pending_charts'):
            charts = agent.pop_pending_charts()
            for chart_buf in charts:
                try:
                    await update.message.reply_photo(photo=chart_buf)
                except Exception as e:
                    logger.warning(f"Failed sending chart photo to user {user_id}: {e}")

        # If AI proposed an action, send confirm keyboard
        if pending:
            from telegram_bot.command_router import CommandRouter
            keyboard = CommandRouter.build_confirm_keyboard(pending.action_id)
            await update.message.reply_text(
                f"*AI Mengusulkan Tindakan:*\n\n{pending.description}\n\n"
                f"_Berlaku selama 90 detik._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )

    # ------------------------------------------------------------------
    # Callback query handler
    # ------------------------------------------------------------------

    async def _resolve_action_agent(self, user_id: int, action_id: str, query: Any) -> Optional[Any]:
        """Resolves the appropriate ChatAgent for an action across topic sessions and memory/DB."""
        thread_id = getattr(query.message, "message_thread_id", None) if query.message else None
        chat_id = query.message.chat_id if query.message else None
        agent = None
        if isinstance(thread_id, int) and chat_id and hasattr(self, "topic_manager") and self.topic_manager:
            topic_session = await self.topic_manager.get_session_for_topic(chat_id, thread_id)
            if topic_session and topic_session in self._chat_agents:
                agent = self._chat_agents[topic_session]
        if not agent:
            agent = self._chat_agents.get(user_id)
        if not agent or action_id not in getattr(agent, "_pending_actions", {}):
            for ag in self._chat_agents.values():
                if action_id in getattr(ag, "_pending_actions", {}):
                    agent = ag
                    break
        if not agent:
            from telegram_bot.chat_agent import ChatAgent
            is_adm = self._router.is_admin(user_id) if hasattr(self._router, "is_admin") else False
            candidate = ChatAgent(self.settings, user_id, is_admin=is_adm)
            persisted = await candidate.get_pending_action(action_id)
            if persisted:
                agent = candidate
                self._chat_agents[user_id] = agent
        return agent

    async def _handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()  # Acknowledge to remove loading spinner

        if not self._is_authorized(update):
            await query.edit_message_text("⛔ Unauthorized.")
            return

        user_id = update.effective_user.id if update.effective_user else 0
        data = query.data or ""

        if data == "cancel":
            await query.edit_message_text("❌ Dibatalkan.")
            return

        if data.startswith("plg:"):
            from harness.installer import (
                list_all_plugins_status,
                toggle_plugin_state,
                run_pip_install,
                get_community_catalog,
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
                lines = ["📦 <b>KATALOG MARKETPLACE PLUG-IN MONIKA</b>\n"]
                kb = []
                for item in catalog:
                    lines.append(f"• <b>{item['name']}</b> (<code>{item['package']}</code>)\n  <i>{item['description']}</i>\n")
                    kb.append([InlineKeyboardButton(f"📥 Install {item['name'][:20]}", callback_data=f"plg:inst:{item['package'][:30]}")])
                kb.append([InlineKeyboardButton("🔌 Plugins Terpasang", callback_data="plg:ref")])
                try:
                    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    pass
                return

            if data.startswith("plg:t:"):
                if not self._is_admin(update):
                    await query.answer("⛔ Hanya Admin yang berhak mengubah status plugin.", show_alert=True)
                    return
                plugin_id = data.split(":", 2)[2]
                plugins = {p["id"]: p for p in list_all_plugins_status()}
                if plugin_id in plugins:
                    p = plugins[plugin_id]
                    if not p.get("can_toggle", True):
                        await query.answer("⚠️ Komponen inti (core) tidak dapat dinonaktifkan.", show_alert=True)
                        return
                    new_state = not p["enabled"]
                    ok, msg = toggle_plugin_state(plugin_id, p["category"], new_state)
                    await query.answer(f"{'🟢 Diaktifkan' if new_state else '⚪ Dinonaktifkan'}: {plugin_id}")
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
                    await query.answer("⛔ Hanya Admin yang berhak menginstall plugin.", show_alert=True)
                    return
                pkg = data.split(":", 2)[2]
                await query.answer(f"Memulai instalasi {pkg}...", show_alert=False)
                await query.edit_message_text(f"⏳ <b>Sedang menginstall via pip:</b> <code>{pkg}</code>...\n<i>Mohon tunggu sebentar...</i>", parse_mode=ParseMode.HTML)
                
                success, out = await asyncio.to_thread(run_pip_install, pkg)
                if success:
                    res_text = f"✅ <b>Instalasi Berhasil:</b> <code>{pkg}</code>\n\n<pre>{out[-300:]}</pre>"
                else:
                    res_text = f"❌ <b>Instalasi Gagal:</b> <code>{pkg}</code>\n\n<pre>{out[-300:]}</pre>"
                
                kb = [[InlineKeyboardButton("🔌 Kembali ke Plugins", callback_data="plg:ref")]]
                await query.edit_message_text(res_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
                return

        if data.startswith("fallback:"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Persetujuan fallback hanya diizinkan untuk Admin.")
                return
            parts = data.split(":")
            if len(parts) >= 3:
                action = parts[1]
                fallback_id = parts[2]
            else:
                action = parts[1]
                fallback_id = None
                
            if not hasattr(self, '_fallback_events') or fallback_id not in self._fallback_events:
                await query.edit_message_text("⚠️ Request fallback ini sudah kedaluwarsa atau dijawab.")
                return
                
            tg_event = self._fallback_events[fallback_id]
            tg_result = self._fallback_results[fallback_id]
            
            if tg_event.is_set():
                await query.edit_message_text("⚠️ Request fallback ini sudah kedaluwarsa atau dijawab dari terminal.")
                return
            
            if action == "once":
                tg_result["approved"] = True
                tg_result["always"] = False
                await query.edit_message_text("✅ Fallback disetujui (1 Siklus).")
            elif action == "always":
                tg_result["approved"] = True
                tg_result["always"] = True
                await query.edit_message_text("✅ Fallback disetujui (Seterusnya).")
            elif action == "reject":
                tg_result["approved"] = False
                tg_result["always"] = False
                await query.edit_message_text("❌ Fallback ditolak.")
            
            tg_event.set()
            
            # Cleanup
            self._fallback_events.pop(fallback_id, None)
            self._fallback_results.pop(fallback_id, None)

        if data.startswith("pause:confirm"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Perintah Pause hanya diizinkan untuk Admin.")
                return
            import time
            parts = data.split(":")
            nonce = parts[2] if len(parts) >= 3 else ""
            reason = "Paused via Telegram"
            if nonce and hasattr(self, '_active_nonces'):
                entry = self._active_nonces.get(nonce)
                exp = entry if isinstance(entry, (int, float)) else (entry.get("expires", 0) if isinstance(entry, dict) else 0)
                if exp < time.time():
                    await query.edit_message_text("⚠️ Konfirmasi jeda trading ini sudah kedaluwarsa.")
                    return
                if isinstance(entry, dict) and "reason" in entry:
                    reason = entry["reason"]
                self._active_nonces.pop(nonce, None)

            from database.db import get_session
            from risk.risk_gate import RiskGate
            gate = RiskGate(self.settings)
            async with get_session() as session:
                await gate.pause_trading(session, reason)
            await query.edit_message_text(f"⏸️ *Trading berhasil dijeda.*\nAlasan: {reason}", parse_mode=ParseMode.MARKDOWN)
            return

        if data.startswith("killswitch:confirm"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Perintah Kill Switch hanya diizinkan untuk Admin.")
                return
            import time
            parts = data.split(":")
            nonce = parts[2] if len(parts) >= 3 else ""
            if nonce and hasattr(self, '_active_nonces'):
                entry = self._active_nonces.get(nonce)
                if not entry:
                    await query.edit_message_text("⚠️ Konfirmasi kill switch ini sudah kedaluwarsa atau telah digunakan.")
                    return
                exp = entry if isinstance(entry, (int, float)) else (entry.get("expires", 0.0) if isinstance(entry, dict) else 0.0)
                if exp < time.time():
                    await query.edit_message_text("⚠️ Konfirmasi kill switch ini sudah kedaluwarsa atau telah digunakan.")
                    self._active_nonces.pop(nonce, None)
                    return
                # Single-use: hapus nonce segera setelah divalidasi
                self._active_nonces.pop(nonce, None)

            await query.edit_message_text("⏳ Menjalankan kill switch...")
            if self.execution_service:
                result = await self.execution_service.kill_switch("Telegram kill switch")
                await query.edit_message_text(
                    f"🛑 *Kill switch selesai.*\n"
                    f"Ditutup: {result['closed']}/{result['total']} posisi",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await query.edit_message_text("⚠️ ExecutionService tidak terhubung.")
            return

        if data.startswith("close:"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Perintah Tutup Posisi hanya diizinkan untuk Admin.")
                return
            ticket = int(data.split(":")[1])
            if self.execution_service:
                result = await self.execution_service.close_position_by_ticket(
                    ticket, requested_by="telegram_admin", reason="Manual close"
                )
                if result.get("success"):
                    await query.edit_message_text(
                        f"✅ Posisi #{ticket} ditutup.\nProfit: {result.get('profit', 'N/A')}",
                    )
                else:
                    await query.edit_message_text(f"❌ Gagal tutup: {result.get('error')}")
            else:
                await query.edit_message_text("⚠️ ExecutionService tidak terhubung.")
            return

        if data.startswith("confirm:"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Konfirmasi aksi hanya diizinkan untuk Admin.")
                return
            action_id = data.split(":", 1)[1]

            from risk.approval_hub import ApprovalHub
            hub = ApprovalHub.get_instance()
            if hub.get_request(action_id):
                await query.edit_message_text(f"⏳ Mengeksekusi via ApprovalHub [{action_id}]...")
                success, msg = await hub.approve(action_id, operator=f"tg_{user_id}")
                await query.edit_message_text(f"{'✅' if success else '❌'} {msg}")
                return

            agent = await self._resolve_action_agent(user_id, action_id, query)
            if not agent:
                if action_id.isdigit() and self.execution_service:
                    await query.edit_message_text(f"⏳ Mengeksekusi analisis #{action_id}...")
                    try:
                        res = await self.execution_service.execute_by_analysis_id(int(action_id))
                        await query.edit_message_text(f"✅ {res.summary() if hasattr(res, 'summary') else str(res)}")
                    except Exception as exec_err:
                        await query.edit_message_text(f"❌ Gagal eksekusi #{action_id}: {exec_err}")
                    return
                await query.edit_message_text("❌ Sesi tidak ditemukan.")
                return
            await query.edit_message_text("⏳ Mengeksekusi...")
            success, msg = await agent.confirm_action(action_id)
            await query.edit_message_text(msg)
            return

        if data.startswith("allow_session:"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Konfirmasi aksi hanya diizinkan untuk Admin.")
                return
            action_id = data.split(":", 1)[1]
            agent = await self._resolve_action_agent(user_id, action_id, query)
            if not agent:
                if action_id.isdigit() and self.execution_service:
                    await query.edit_message_text(f"⏳ Mengeksekusi analisis #{action_id}...")
                    try:
                        res = await self.execution_service.execute_by_analysis_id(int(action_id))
                        await query.edit_message_text(f"✅ {res.summary() if hasattr(res, 'summary') else str(res)}")
                    except Exception as exec_err:
                        await query.edit_message_text(f"❌ Gagal eksekusi #{action_id}: {exec_err}")
                    return
                await query.edit_message_text("❌ Sesi tidak ditemukan.")
                return
            await query.edit_message_text("⏳ Mengeksekusi dan mengaktifkan izin sesi (4h)...")
            success, msg = await agent.approve_for_session(action_id)
            await query.edit_message_text(msg)
            return

        if data.startswith("reject:"):
            if not self._is_admin(update):
                await query.edit_message_text("⛔ Penolakan aksi hanya diizinkan untuk Admin.")
                return
            action_id = data.split(":", 1)[1]

            from risk.approval_hub import ApprovalHub
            hub = ApprovalHub.get_instance()
            if hub.get_request(action_id):
                success, msg = await hub.reject(action_id, operator=f"tg_{user_id}", reason="Dibatalkan via Telegram")
                await query.edit_message_text(f"❌ Permintaan [{action_id}] telah dibatalkan.")
                return

            agent = await self._resolve_action_agent(user_id, action_id, query)
            if not agent:
                if action_id.isdigit():
                    from database.db import get_session
                    from database.models import ActivityLog, AssetAnalysis, PaperTradeRecord
                    from sqlalchemy import update as sql_update
                    async with get_session() as session:
                        session.add(ActivityLog(
                            category="trading",
                            description=f"Trade proposal #{action_id} REJECTED by admin via Telegram inline button",
                            actor="telegram_admin",
                        ))
                        try:
                            await session.execute(
                                sql_update(AssetAnalysis)
                                .where(AssetAnalysis.id == int(action_id))
                                .values(execution_status='rejected', execution_notes='Rejected via Telegram inline button')
                            )
                            await session.execute(
                                sql_update(PaperTradeRecord)
                                .where(PaperTradeRecord.analysis_id == int(action_id))
                                .where(PaperTradeRecord.status == 'open')
                                .values(
                                    status='closed',
                                    closed_at=datetime.now(timezone.utc),
                                    exit_reason='rejected_by_admin',
                                    pnl_pct=0.0,
                                )
                            )
                        except Exception:
                            pass
                        await session.commit()
                    await query.edit_message_text(f"❌ Analisis #{action_id} ditolak.")
                    return
                await query.edit_message_text("❌ Sesi tidak ditemukan.")
                return
            msg = await agent.reject_action(action_id)
            await query.edit_message_text(f"❌ {msg}")
            return

        await query.edit_message_text("❓ Callback tidak dikenali.")

    # ------------------------------------------------------------------
    # Data builders (read-only DB queries)
    # ------------------------------------------------------------------

    async def _build_status_text(self) -> str:
        from database.db import get_session
        from database.models import Position, RiskState, AssetAnalysis
        from sqlalchemy import select, func
        from telegram_bot.vintage_formatter import format_status_slip

        try:
            async with get_session() as session:
                now = datetime.now(timezone.utc)

                # Open positions count
                pos_count = (await session.execute(
                    select(func.count(Position.id)).where(Position.status == "open")
                )).scalar_one_or_none() or 0

                # Risk state
                today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                risk  = (await session.execute(
                    select(RiskState).where(RiskState.date >= today)
                    .order_by(RiskState.date.desc()).limit(1)
                )).scalar_one_or_none()

                # Last analysis
                last_analysis = (await session.execute(
                    select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(1)
                )).scalar_one_or_none()

                status_txt  = "DIJEDA" if (risk and risk.trading_paused) else "AKTIF"
                daily_pnl  = f"${risk.daily_pnl:+.2f}" if risk else "$0.00"
                drawdown   = f"${risk.current_drawdown:.2f}" if risk else "$0.00"

                last_ts = last_analysis.generated_at.strftime("%d %b %Y %H:%M UTC") \
                          if last_analysis else "Belum ada"

                return format_status_slip(
                    status_text=status_txt,
                    pos_count=pos_count,
                    daily_pnl=daily_pnl,
                    drawdown=drawdown,
                    last_analysis=last_ts,
                    now_str=now.strftime("%Y-%m-%d %H:%M UTC"),
                )
        except Exception as e:
            return f"[ GAGAL ] Error mengambil status: {e}"

    async def _build_positions_text(self) -> str:
        from database.db import get_session
        from database.models import Position
        from sqlalchemy import select
        from telegram_bot.vintage_formatter import format_positions_slip

        try:
            async with get_session() as session:
                positions = (await session.execute(
                    select(Position).where(Position.status == "open")
                    .order_by(Position.opened_at.desc())
                )).scalars().all()

                return format_positions_slip(positions)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_brief_text(self) -> str:
        from database.db import get_session
        from database.models import FundamentalBrief
        from sqlalchemy import select

        try:
            async with get_session() as session:
                brief = (await session.execute(
                    select(FundamentalBrief)
                    .order_by(FundamentalBrief.generated_at.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if not brief:
                    return "```\n[ NIHIL ] Belum ada fundamental brief yang dihasilkan.\n```"

                ts = brief.generated_at.strftime("%d %b %Y %H:%M UTC") if brief.generated_at else "?"
                content = brief.content_markdown or "(tidak ada konten)"
                return f"```\nMONIKA DISPATCH // FUNDAMENTAL BRIEF\nWAKTU: {ts}\n" + "=" * 46 + f"\n{content}\n```"
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_analysis_text(self, symbol: str) -> str:
        from database.db import get_session
        from database.models import AssetAnalysis
        from sqlalchemy import select
        
        try:
            async with get_session() as session:
                analysis = (await session.execute(
                    select(AssetAnalysis)
                    .where(AssetAnalysis.symbol == symbol)
                    .order_by(AssetAnalysis.generated_at.desc())
                    .limit(1)
                )).scalar_one_or_none()
                
                if not analysis:
                    return f"```\n[ NIHIL ] Belum ada analisis untuk {symbol}.\n```"
                    
                ts = analysis.generated_at.strftime("%d %b %Y %H:%M UTC") if analysis.generated_at else "?"
                decision = analysis.decision.upper() if analysis.decision else "N/A"
                confidence = f"{analysis.confidence:.0%}" if analysis.confidence is not None else "N/A"
                
                content = getattr(analysis, "content_markdown", None)
                if not content:
                    content = getattr(analysis, "rationale", "(tidak ada detail)")
                
                return f"```\nMONIKA DISPATCH // ANALISIS: {symbol}\nWAKTU: {ts}\nKEPUTUSAN: [ {decision} ] (Conf: {confidence})\n" + "=" * 46 + f"\n{content}\n```"
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_history_text(self) -> str:
        from database.db import get_session
        from database.models import ActivityLog
        from sqlalchemy import select

        try:
            async with get_session() as session:
                logs = (await session.execute(
                    select(ActivityLog)
                    .order_by(ActivityLog.timestamp.desc())
                    .limit(10)
                )).scalars().all()

                if not logs:
                    return "```\n[ NIHIL ] Belum ada aktivitas yang tercatat.\n```"

                lines = [
                    "```",
                    "=" * 46,
                    "MONIKA DISPATCH // AKTIVITAS TERAKHIR (10)",
                    "=" * 46,
                ]
                for log in logs:
                    ts   = log.timestamp.strftime("%d/%m %H:%M") if log.timestamp else "?"
                    desc = log.description[:60] if log.description else ""
                    cat  = log.category or "system"
                    lines.append(f"[{cat.upper()[:6].ljust(6)}] {ts} : {desc}")
                lines.append("=" * 46)
                lines.append("```")
                return "\n".join(lines)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_risk_text(self) -> str:
        from database.db import get_session
        from database.models import RiskState
        from sqlalchemy import select
        from utils.analytics.paper_tracker import PaperTracker
        from telegram_bot.vintage_formatter import format_risk_slip

        try:
            async with get_session() as session:
                today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                risk  = (await session.execute(
                    select(RiskState).where(RiskState.date >= today)
                    .order_by(RiskState.date.desc()).limit(1)
                )).scalar_one_or_none()

                tracker = PaperTracker(self.settings)
                suspended = await tracker.get_suspended_symbols(session)
                
                paper_cfg = self.settings.get('trading', {}).get('paper_trading', {})
                streak_policy = paper_cfg.get('streak_loss_policy', 'warn_and_scale')
                auto_exec = self.settings.get('trading', {}).get('auto_execute', False)

                status_txt = "DIJEDA" if (risk and risk.trading_paused) else "AKTIF"
                daily_pnl = f"${risk.daily_pnl:+.2f}" if risk else None
                drawdown = f"${risk.current_drawdown:.2f}" if risk else None
                reason = risk.reason if (risk and risk.reason) else None

                return format_risk_slip(
                    status_text=status_txt,
                    mode="LIVE" if auto_exec else "PAPER",
                    streak_policy=streak_policy,
                    suspended_symbols=suspended,
                    daily_pnl=daily_pnl,
                    drawdown=drawdown,
                    reason=reason,
                )
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_risk_deep_text(self) -> str:
        from database.db import get_session
        from risk.risk_gate import RiskGate
        from telegram_bot.vintage_formatter import format_risk_deep_slip

        try:
            gate = RiskGate(self.settings)
            async with get_session() as session:
                scorecard = await gate.get_current_scorecard(session)
            
            # Statistical edge info
            edge_summary = None
            try:
                from utils.analytics.paper_tracker import PaperTracker
                tracker = PaperTracker(self.settings)
                async with get_session() as session:
                    stats = await tracker.get_stats(session)
                    edge_summary = {
                        "expectancy": f"{stats.get('expectancy_per_trade_R', 0):+.2f}R",
                        "win_rate": f"{stats.get('win_rate_pct', 0):.1f}%",
                    }
            except Exception:
                pass

            # Token budget info
            token_budget = None
            try:
                from logging_observability.token_budgeter import TokenBudgetManager
                tbm = TokenBudgetManager.get_instance()
                summary = tbm.get_budget_summary()
                token_budget = {
                    "tier": "NORMAL" if summary.get("total_pct_used", 0) < 70 else ("COMPRESSED" if summary.get("total_pct_used", 0) < 90 else "DEGRADED"),
                    "capacity_pct": max(0, 100 - summary.get("total_pct_used", 0)),
                }
            except Exception:
                pass

            return format_risk_deep_slip(scorecard, edge_summary=edge_summary, token_budget=token_budget)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_approvals_text(self) -> str:
        from risk.approval_hub import ApprovalHub
        from telegram_bot.vintage_formatter import format_approvals_slip

        try:
            hub = ApprovalHub.get_instance()
            open_reqs = hub.get_open_requests()
            return format_approvals_slip(open_reqs)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_trailing_text(self) -> str:
        from database.db import get_session
        from database.models import Position
        from sqlalchemy import select
        from telegram_bot.vintage_formatter import format_trailing_slip

        try:
            async with get_session() as session:
                stmt = select(Position).where(Position.closed_at.is_(None)).order_by(Position.opened_at.desc())
                positions = (await session.execute(stmt)).scalars().all()
                pos_list = []
                for p in positions:
                    pos_list.append({
                        "ticket": getattr(p, "mt5_ticket", getattr(p, "ticket", p.id)),
                        "symbol": p.symbol,
                        "direction": p.direction,
                        "entry_price": p.entry_price,
                        "current_sl": p.sl or "-",
                        "be_triggered": p.sl is not None and ((p.direction == "buy" and p.sl >= p.entry_price) or (p.direction == "sell" and p.sl <= p.entry_price)),
                        "atr_distance": getattr(p, "atr_trailing_distance", "-"),
                    })
                return format_trailing_slip(pos_list)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_reconcile_text(self) -> str:
        from scheduler.order_reconciler import OrderReconciler
        from telegram_bot.vintage_formatter import format_reconcile_slip

        try:
            reconciler = OrderReconciler(settings=self.settings, execution_service=self.execution_service)
            stats = await reconciler.reconcile_once()
            return format_reconcile_slip(stats)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_fedwatch_text(self) -> str:
        from database.db import get_session
        from database.models import FedWatchProbability, CentralBankRateExpectation
        from sqlalchemy import select
        from telegram_bot.vintage_formatter import format_fedwatch_slip
        import json

        try:
            async with get_session() as session:
                fw_rows = (await session.execute(
                    select(FedWatchProbability).order_by(FedWatchProbability.fetched_at.desc()).limit(5)
                )).scalars().all()
                cb_rows = (await session.execute(
                    select(CentralBankRateExpectation).order_by(CentralBankRateExpectation.fetched_at.desc()).limit(5)
                )).scalars().all()

                fw_data = []
                for p in fw_rows:
                    probs = p.probabilities_json
                    if isinstance(probs, str):
                        try:
                            probs = json.loads(probs)
                        except Exception:
                            probs = {}
                    fw_data.append({
                        "meeting_date": p.meeting_date,
                        "probabilities": probs,
                    })

                cb_data = [
                    {
                        "bank": cb.bank,
                        "current_rate": cb.current_rate,
                        "prob_cut": cb.prob_cut,
                    }
                    for cb in cb_rows
                ]
                return format_fedwatch_slip({"fedwatch": fw_data, "central_banks": cb_data})
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_yields_text(self) -> str:
        from database.db import get_session
        from database.models import TreasuryYield, BondYieldData
        from sqlalchemy import select
        from telegram_bot.vintage_formatter import format_yields_slip

        try:
            async with get_session() as session:
                y_rows = (await session.execute(
                    select(TreasuryYield).order_by(TreasuryYield.date.desc()).limit(30)
                )).scalars().all()
                b_rows = (await session.execute(
                    select(BondYieldData).order_by(BondYieldData.date.desc()).limit(10)
                )).scalars().all()

                latest: dict = {}
                for y in y_rows:
                    if y.tenor not in latest:
                        latest[y.tenor] = y

                y2 = latest.get("2Y")
                y10 = latest.get("10Y")
                spread = round(y10.yield_percent - y2.yield_percent, 3) if (y2 and y10) else None

                return format_yields_slip({
                    "treasury_yields": [{"tenor": y.tenor, "yield_percent": y.yield_percent} for y in latest.values()],
                    "spread_2s10s": spread,
                    "is_inverted": (spread < 0.0) if spread is not None else False,
                    "global_bonds": [{"country_tenor": b.country_tenor, "yield_percent": b.yield_percent} for b in b_rows],
                })
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_fear_greed_text(self) -> str:
        from database.db import get_session
        from database.models import SystemConfig
        from sqlalchemy import select
        from telegram_bot.vintage_formatter import format_fear_greed_slip
        import json

        try:
            async with get_session() as session:
                cfg = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == "fear_greed_latest").limit(1)
                )).scalar_one_or_none()
                if cfg and cfg.value:
                    data = json.loads(cfg.value)
                    return format_fear_greed_slip(data)
                return format_fear_greed_slip({"current_value": 50, "classification": "Neutral", "wow_change": 0})
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_cot_text(self, market_code: Optional[str] = None) -> str:
        from database.db import get_session
        from database.models import COTReport
        from sqlalchemy import select
        from telegram_bot.vintage_formatter import format_cot_slip

        try:
            async with get_session() as session:
                q = select(COTReport)
                if market_code:
                    q = q.where(COTReport.market_code == market_code.upper())
                q = q.order_by(COTReport.report_date.desc()).limit(10)
                records = (await session.execute(q)).scalars().all()

                data = [
                    {
                        "market_code": r.market_code,
                        "asset_mgr_long": r.asset_mgr_long,
                        "asset_mgr_short": r.asset_mgr_short,
                        "leveraged_long": r.leveraged_long,
                        "leveraged_short": r.leveraged_short,
                        "net_position": (r.asset_mgr_long + r.leveraged_long) - (r.asset_mgr_short + r.leveraged_short),
                    }
                    for r in records
                ]
                return format_cot_slip(data)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_playbooks_text(self) -> str:
        from telegram_bot.vintage_formatter import format_playbooks_slip
        try:
            from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager
            mgr = PlaybookLifecycleManager()
            all_pb = mgr.list_all_playbooks()
            items = []
            for name, meta in all_pb.items():
                items.append({
                    "name": name,
                    "status": meta.status.value if hasattr(meta.status, "value") else str(meta.status),
                    "win_rate": getattr(meta, "win_rate", 0.0),
                    "total_trades": getattr(meta, "total_trades", 0),
                    "cooldown_until": meta.cooldown_until.isoformat() if getattr(meta, "cooldown_until", None) else None,
                })
            return format_playbooks_slip(items)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_rollback_text(self, name: str) -> str:
        from telegram_bot.vintage_formatter import format_rollback_slip
        try:
            from analysis.memory.playbook_ledger import PlaybookLedger
            ledger = PlaybookLedger()
            success = ledger.rollback(name)
            res = {
                "name": name,
                "status": "SUCCESS" if success else "FAILED",
                "message": f"Rolled back playbook '{name}' to prior ledger checkpoint." if success else f"No previous history snapshot found for '{name}'."
            }
            return format_rollback_slip(res)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_crystallized_text(self) -> str:
        from telegram_bot.vintage_formatter import format_crystallized_slip
        try:
            from analysis.memory.skill_crystallizer import SkillCrystallizer
            import yaml
            crystallizer = SkillCrystallizer()
            skills_dir = crystallizer.SKILLS_DIR
            items = []
            if skills_dir.exists():
                for f in sorted(skills_dir.glob("*.md")):
                    try:
                        content = f.read_text(encoding="utf-8")
                        meta = {}
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                meta = yaml.safe_load(parts[1]) or {}
                        clean_name = f.stem.lower()
                        items.append({
                            "name": meta.get("name", clean_name),
                            "symbol": meta.get("symbol", "-"),
                            "status": meta.get("status", "active"),
                            "is_deprecated": meta.get("is_deprecated", False),
                            "win_rate": float(meta.get("win_count", 1.0)) / max(1.0, float(meta.get("win_count", 1.0))),
                            "total_pnl_usd": float(meta.get("total_pnl_usd", 0.0)),
                        })
                    except Exception:
                        pass
            return format_crystallized_slip(items)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_vix_text(self) -> str:
        from database.db import get_session
        from database.models import VIXData
        from sqlalchemy import select

        try:
            async with get_session() as session:
                vix_rows = (await session.execute(
                    select(VIXData).order_by(VIXData.date.desc()).limit(5)
                )).scalars().all()

                if not vix_rows:
                    return "📉 *Data VIX belum tersedia.*"

                lines = ["*📉 VIX (5 Data Terakhir)*\n"]
                for v in vix_rows:
                    date_str = v.date.strftime("%d %b") if v.date else "?"
                    close    = f"{v.close:.2f}" if v.close is not None else "?"
                    # VIX interpretation
                    if v.close and v.close > 30:
                        icon = "🔴"
                    elif v.close and v.close > 20:
                        icon = "🟡"
                    else:
                        icon = "🟢"
                    lines.append(f"{icon} `{date_str}`: VIX = *{close}*")
                return "\n".join(lines)
        except Exception as e:
            return f"❌ Error: {e}"

    async def _build_tokens_text(self) -> str:
        try:
            from utils.analytics.token_auditor import TokenAuditor
            summary = await TokenAuditor.get_summary(hours=24)
            if not summary or summary["total_calls"] == 0:
                return "📊 *Belum ada konsumsi token tercatat hari ini (24 jam terakhir).*"

            lines = ["*📊 Laporan Konsumsi Token (24 Jam Terakhir)*\n"]
            lines.append(f"• *Total Panggilan*: {summary['total_calls']:,} calls")
            lines.append(f"• *Total Input*: {summary['input_tokens']:,} tokens")
            lines.append(f"• *Total Output*: {summary['output_tokens']:,} tokens")
            lines.append(f"• *Total Akumulasi*: {summary['total_tokens']:,} tokens")
            if summary['cached_tokens'] > 0:
                lines.append(f"• *Prompt Caching*: {summary['cached_tokens']:,} tokens ({summary['cache_hit_rate_pct']:.1f}% hemat)")
            lines.append(f"• *Estimasi Biaya*: `${summary['total_cost_usd']:.4f} USD`\n")

            # Subsystem Breakdown
            subsystems = await TokenAuditor.get_subsystem_breakdown(hours=24)
            if subsystems:
                lines.append("*📂 Berdasarkan Subsystem:*")
                for s in subsystems[:6]:
                    lines.append(f"  ▫️ *{s['subsystem']}*: {s['sum_total']:,} tokens (${s['sum_cost_usd']:.4f} | {s['pct_cost']:.1f}%)")
                lines.append("")

            # Top Roles Breakdown
            roles = await TokenAuditor.get_role_breakdown(hours=24)
            if roles:
                lines.append("*🤖 Top Task Roles Terbesar:*")
                for r in roles[:5]:
                    lines.append(f"  ▫️ `{r['task_role']}`: {r['calls']} calls, avg {r['avg_total']:,.0f} tok (${r['sum_cost_usd']:.4f})")

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error: {e}"

    async def _build_credits_text(self) -> str:
        try:
            from utils.api.credit_balance_tracker import CreditBalanceTracker
            rep = await CreditBalanceTracker.get_full_credit_report()

            lines = ["*💳 LAPORAN SISA KREDIT & KUOTA API*\n"]

            # 1. Live Provider Balances (Tier Berbayar)
            lines.append("*🔹 Saldo Live Provider (Tier Berbayar):*")
            
            # OpenRouter Paid Key
            or_data = rep.get("openrouter", {})
            paid_status = or_data.get("paid_key", {})
            if paid_status.get("status") == "ok":
                rem = paid_status.get("remaining_usd", 0.0)
                tot = paid_status.get("total_credits_usd", 0.0)
                usg = paid_status.get("total_usage_usd", 0.0)
                lines.append(f"• *OpenRouter (Paid Key)*: `${rem:.2f} USD` tersisa (Total: `${tot:.2f}` | Terpakai: `${usg:.2f}`)")
            elif paid_status.get("status") == "insufficient_credits":
                lines.append("• *OpenRouter (Paid Key)*: ⚠️ `$0.00 USD` (Saldo top-up habis)")
            elif not paid_status.get("configured"):
                lines.append("• *OpenRouter (Paid Key)*: _OPENROUTER_PAID_API_KEY belum disetel_")
            else:
                lines.append(f"• *OpenRouter (Paid Key)*: ⚠️ Status: {paid_status.get('message', 'Error')}")

            # DeepSeek
            ds_data = rep.get("deepseek", {})
            if ds_data.get("status") == "ok":
                tot_bal = ds_data.get("total_balance_usd", 0.0)
                top_bal = ds_data.get("topped_up_balance_usd", 0.0)
                grant_bal = ds_data.get("granted_balance_usd", 0.0)
                lines.append(f"• *DeepSeek*: `${tot_bal:.2f} USD` tersisa (Top-up: `${top_bal:.2f}` | Bonus: `${grant_bal:.2f}`)")
            elif ds_data.get("status") == "unconfigured":
                lines.append("• *DeepSeek*: _API Key tidak aktif / opsional_")
            else:
                lines.append(f"• *DeepSeek*: ⚠️ Status: {ds_data.get('message', 'Error')}")

            lines.append("")

            # 2. Pool Kunci Gratisan OpenRouter (Free Tier Models)
            free_keys = or_data.get("free_keys", {})
            if free_keys.get("configured_count", 0) > 0:
                act = free_keys.get("active_count", 0)
                cfg = free_keys.get("configured_count", 0)
                icon = "🟢" if act == cfg else ("🟡" if act > 0 else "🔴")
                lines.append("*🔹 Pool Kunci Gratisan OpenRouter (Free Tier Models):*")
                lines.append(f"{icon} *OpenRouter Free Keys*: `{act} / {cfg}` Kunci Aktif & Siap (`is_free_tier: true`)")
                lines.append("")

            # 3. Sisa Kuota Harian Free Tier (Hari ini)
            quotas = rep.get("quotas", {})
            if quotas:
                lines.append("*🔹 Sisa Kuota Harian Free Tier (Hari Ini):*")
                key_models = ["gemini-3.7-flash", "gemini-3.5-flash-lite", "groq-compound", "qwen3.8-27b"]
                for km in key_models:
                    if km in quotas:
                        q = quotas[km]
                        icon = "🟢" if q["pct_used"] < 70 else ("🟡" if q["pct_used"] < 90 else "🔴")
                        lines.append(f"{icon} `{km}`: *{q['remaining_calls']}* / {q['rpd_limit']} RPD tersisa ({q['used_calls']} calls)")
                lines.append("")

            # 3. Akumulasi Pengeluaran Bulan Ini
            expenses = rep.get("expenses", {})
            if expenses:
                m_str = expenses.get("month_str", "Bulan Ini")
                tot_cost = expenses.get("total_month_usd", 0.0)
                tot_calls = expenses.get("total_month_calls", 0)
                lines.append(f"*🔹 Akumulasi Pengeluaran ({m_str}):* `${tot_cost:.4f} USD` ({tot_calls:,} calls)")
                by_prov = expenses.get("by_provider", {})
                for prov, pdata in sorted(by_prov.items(), key=lambda x: x[1].get("cost_usd", 0), reverse=True):
                    lines.append(f"  ▫️ *{prov.title()}*: `${pdata['cost_usd']:.4f}` ({pdata['calls']} calls, {pdata['tokens']:,} tok)")

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error Credit Balance Tracker: {e}"


    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _balance_markdown_chunk(chunk: str) -> str:
        """Ensure any unclosed markdown tags within a single chunk are closed safely."""
        if not chunk:
            return ""

        # 1. Balance code blocks (```)
        cb_matches = re.findall(r"```(\w*)", chunk)
        if len(cb_matches) % 2 == 1:
            chunk += "\n```"

        # 2. Balance inline code (`)
        no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
        if no_cb.count("`") % 2 == 1:
            chunk += "`"

        # 3. Balance bold (*) outside code blocks and inline code
        no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
        no_inline = re.sub(r"`.*?`", "", no_cb, flags=re.DOTALL)
        if no_inline.count("*") % 2 == 1:
            chunk += "*"

        # 4. Balance italic (_) outside code blocks and inline code
        no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
        no_inline = re.sub(r"`.*?`", "", no_cb, flags=re.DOTALL)
        if no_inline.count("_") % 2 == 1:
            chunk += "_"

        return chunk

    @staticmethod
    def _chunk_text(
        text: str,
        max_len: int = 4000,
        sanitize_format: bool = False,
        is_html: bool = False,
    ) -> list[str]:
        """Split text into Telegram-safe chunks while preserving formatting boundaries."""
        if not text:
            return []
        if sanitize_format:
            from telegram_bot.chat_agent import _sanitize_telegram_format
            text = _sanitize_telegram_format(text)
        
        balance_fn = (lambda s: s) if is_html else TelegramBot._balance_markdown_chunk
        if len(text) <= max_len:
            return [balance_fn(text)]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= max_len:
                chunks.append(balance_fn(remaining))
                break

            # Find best split point (prefer double newline, then single newline, then space)
            split_at = remaining.rfind("\n\n", 0, max_len)
            if split_at != -1 and split_at >= max_len // 2:
                split_len = split_at + 2
            else:
                split_at = remaining.rfind("\n", 0, max_len)
                if split_at != -1 and split_at >= max_len // 3:
                    split_len = split_at + 1
                else:
                    split_at = remaining.rfind(" ", 0, max_len)
                    if split_at != -1 and split_at >= max_len // 3:
                        split_len = split_at + 1
                    else:
                        split_len = max_len

            chunk = remaining[:split_len].rstrip()
            next_remaining = remaining[split_len:].lstrip()

            if not is_html:
                # Balance code blocks (```)
                cb_matches = re.findall(r"```(\w*)", chunk)
                if len(cb_matches) % 2 == 1:
                    last_cb = list(re.finditer(r"```(\w*)", chunk))[-1]
                    lang = last_cb.group(1) or ""
                    chunk += "\n```"
                    next_remaining = f"```{lang}\n" + next_remaining

                # Balance inline code (`)
                no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
                no_cb = re.sub(r"```.*$", "", no_cb, flags=re.DOTALL)
                if no_cb.count("`") % 2 == 1:
                    chunk += "`"
                    next_remaining = "`" + next_remaining

                # Balance bold (*)
                no_inline = re.sub(r"`.*?`", "", no_cb)
                if no_inline.count("*") % 2 == 1:
                    chunk += "*"
                    next_remaining = "*" + next_remaining

                # Balance italic (_)
                if no_inline.count("_") % 2 == 1:
                    chunk += "_"
                    next_remaining = "_" + next_remaining

            chunks.append(chunk)
            remaining = next_remaining

        return chunks

    async def _cmd_approve(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)
        
        if not ctx.args:
            await update.message.reply_text("Usage: /approve <analysis_id>")
            return
        
        try:
            analysis_id = int(ctx.args[0])
        except ValueError:
            await update.message.reply_text("❌ analysis_id harus berupa angka.")
            return
        
        if not self.execution_service:
            await update.message.reply_text("⚠️ ExecutionService tidak terhubung.")
            return
        
        await update.message.reply_text(f"⏳ Mengeksekusi analisis #{analysis_id}...")
        try:
            result = await self.execution_service.execute_by_analysis_id(analysis_id)
            try:
                from risk.approval_hub import ApprovalHub
                user_id = update.effective_user.id if update.effective_user else "unknown"
                await ApprovalHub.get_instance().approve(str(analysis_id), operator=f"telegram:{user_id}")
            except Exception:
                pass
            await update.message.reply_text(
                f"✅ {result.summary()}" if hasattr(result, 'summary') else str(result)
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal: {e}")

    async def _cmd_reject(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)
        
        if not ctx.args:
            await update.message.reply_text("Usage: /reject <analysis_id>")
            return
        
        analysis_id_str = ctx.args[0]
        
        try:
            from risk.approval_hub import ApprovalHub
            user_id = update.effective_user.id if update.effective_user else "unknown"
            await ApprovalHub.get_instance().reject(str(analysis_id_str), operator=f"telegram:{user_id}", reason="Rejected via Telegram by admin")
        except Exception:
            pass

        from database.db import get_session
        async with get_session() as session:
            from database.models import ActivityLog, PaperTradeRecord
            from sqlalchemy import select, update as sql_update
            
            session.add(ActivityLog(
                category="trading",
                description=f"Trade proposal #{analysis_id_str} REJECTED by admin via Telegram",
                actor="telegram_admin",
            ))
            
            try:
                analysis_id = int(analysis_id_str)
                
                from database.models import AssetAnalysis
                await session.execute(
                    sql_update(AssetAnalysis)
                    .where(AssetAnalysis.id == analysis_id)
                    .values(execution_status='rejected', execution_notes='Rejected via Telegram by admin')
                )
                
                await session.execute(
                    sql_update(PaperTradeRecord)
                    .where(PaperTradeRecord.analysis_id == analysis_id)
                    .where(PaperTradeRecord.status == 'open')
                    .values(
                        status='closed',
                        closed_at=datetime.now(timezone.utc),
                        exit_reason='rejected_by_admin',
                        pnl_pct=0.0,
                    )
                )
            except (ValueError, Exception) as e:
                logger.debug(f"Paper trade cleanup on reject (non-fatal): {e}")
            
            await session.commit()
        
        await update.message.reply_text(f"❌ Analisis #{analysis_id_str} ditolak dan tidak akan dieksekusi.")

    async def _cmd_steer(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Mid-stream in-flight steer directive synchronized across Telegram, WS, and TUI."""
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        if not self._is_admin(update): return await self._reject_non_admin(update)

        if not ctx.args or len(ctx.args) < 2:
            await update.message.reply_text(
                "Usage: `/steer <symbol> <instruction>`\nContoh: `/steer EURUSD prioritize bearish sweep reclaim`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        symbol = ctx.args[0].upper().strip()
        instruction = " ".join(ctx.args[1:]).strip()

        from risk.approval_hub import ApprovalHub
        user_id = update.effective_user.id if update.effective_user else "unknown"
        operator_tag = f"telegram:{user_id}"
        await ApprovalHub.get_instance().steer(symbol, instruction, operator=operator_tag)

        await update.message.reply_text(
            f"🎯 *Steer Synchronized Across All Surfaces*\n\n"
            f"• *Symbol:* `{symbol}`\n"
            f"• *Instruction:* {instruction}\n"
            f"• *Surfaces:* Telegram, Dashboard CRT, TUI Terminal\n"
            f"• *Status:* Injected into active trading cycle",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_tearsheet(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        days = 30
        if ctx.args and len(ctx.args) > 0:
            try:
                days = max(1, int(ctx.args[0]))
            except ValueError:
                days = 30

        from database.db import get_session
        from database.models import PaperTradeRecord, Position
        from sqlalchemy import select
        from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator

        since = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            async with get_session() as session:
                trades = (await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.closed_at >= since)
                )).scalars().all()

                if not trades:
                    trades = (await session.execute(
                        select(Position)
                        .where(Position.status == "closed")
                        .where(Position.closed_at >= since)
                    )).scalars().all()

            if not trades:
                await update.message.reply_text(f"ℹ️ Belum ada trade closed dalam {days} hari terakhir.")
                return

            tearsheet = QuantTearsheetGenerator.generate_from_trades(trades)
            html_text = tearsheet.to_telegram_html()
            for chunk in self._chunk_text(html_text, is_html=True):
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error executing /tearsheet: {e}")
            await update.message.reply_text(f"❌ Error generating tearsheet: {e}")

    async def _cmd_report(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        if not self._is_authorized(update): return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_weekly_report()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _build_weekly_report(self) -> str:
        from database.db import get_session
        from database.models import Position, PaperTradeRecord, TokenUsageLog, CyclePerformance
        from sqlalchemy import select, func
        from datetime import timedelta
        
        try:
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            
            async with get_session() as session:
                # Closed positions this week
                closed = (await session.execute(
                    select(Position)
                    .where(Position.status == "closed")
                    .where(Position.closed_at >= week_ago)
                )).scalars().all()

                paper_closed = (await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.closed_at >= week_ago)
                )).scalars().all()
                
                total_pnl = sum(p.pnl or 0 for p in closed)
                wins = [p for p in closed if (p.pnl or 0) > 0]
                losses = [p for p in closed if (p.pnl or 0) <= 0]
                win_rate = len(wins) / len(closed) * 100 if closed else 0
                
                # Token usage this week
                tok_result = (await session.execute(
                    select(
                        TokenUsageLog.provider,
                        func.sum(TokenUsageLog.total_tokens).label("total"),
                    )
                    .where(TokenUsageLog.timestamp >= week_ago)
                    .group_by(TokenUsageLog.provider)
                )).all()
                
                # Cycle stats this week
                cycles = (await session.execute(
                    select(func.count(CyclePerformance.id))
                    .where(CyclePerformance.cycle_at >= week_ago)
                )).scalar_one_or_none() or 0
                
                avg_cost_q = (await session.execute(
                    select(func.avg(CyclePerformance.api_cost_usd))
                    .where(CyclePerformance.cycle_at >= week_ago)
                    .where(CyclePerformance.api_cost_usd != None)
                )).scalar_one_or_none()
                
            lines = [
                f"*📊 Weekly Report — {week_ago.strftime('%d %b')} to {now.strftime('%d %b %Y')}*\n",
                f"*Trading Performance:*",
                f"  Closed trades: {len(closed)}",
                f"  Win rate: {win_rate:.1f}%",
                f"  Total P&L: `{'${:+.2f}'.format(total_pnl)}`",
                f"  Winners: {len(wins)} | Losers: {len(losses)}",
                "",
            ]
            
            # Fetch tracker stats for expectancy and suspended symbols
            try:
                from utils.analytics.paper_tracker import PaperTracker
                tracker = PaperTracker()
                async with get_session() as tracker_session:
                    stats = await tracker.get_statistics(tracker_session)
                    exp = stats.get('expectancy_per_trade_R')
                    if exp is not None:
                        lines.append("*Edge Status:*")
                        if exp > 0:
                            lines.append(f"  🟢 EDGE POSITIVE: Expectancy = +{exp:.2f}R per trade")
                        elif exp > -0.1:
                            lines.append(f"  🟡 EDGE UNCERTAIN: Expectancy = {exp:.2f}R per trade")
                        else:
                            lines.append(f"  🔴 EDGE NEGATIVE: Expectancy = {exp:.2f}R per trade — AUTO-SUSPEND RISK")
                    
                    suspended = await tracker.get_suspended_symbols(tracker_session)
                    if suspended:
                        lines.append(f"  ⏸️ Suspended Symbols: {', '.join(suspended)}")
                    lines.append("")
                    
                    from utils.analytics.analysis_tracker import get_direction_accuracy_report
                    dir_acc = await get_direction_accuracy_report(tracker_session, 7)
                    if dir_acc and "error" not in dir_acc and not dir_acc.get('insufficient_data'):
                        lines.append("*Analysis Quality:*")
                        lines.append(f"  🎯 Direction Accuracy (4h): {dir_acc.get('direction_accuracy_4h', dir_acc.get('overall_accuracy_4h_pct'))}%")
                        brier = dir_acc.get('brier_score', dir_acc.get('mean_brier_score'))
                        if brier is not None:
                            # Brier score: 0 is perfect, 1 is totally wrong, 0.25 is random guessing
                            lines.append(f"  🧠 Confidence Brier Score: {brier:.3f} (closer to 0 is better)")
                        lines.append("")
            except Exception as e:
                logger.debug(f"Failed to fetch tracker stats for report: {e}")

            try:
                from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator
                report_trades = closed if closed else paper_closed
                if report_trades:
                    ts = QuantTearsheetGenerator.generate_from_trades(report_trades)
                    lines.append("*Quant Tearsheet Highlights:*")
                    lines.append(f"  Sharpe: `{ts.annualized_sharpe:.2f}` | Sortino: `{ts.annualized_sortino:.2f}` | Calmar: `{ts.calmar_ratio:.2f}`")
                    lines.append(f"  Max DD: `{ts.max_drawdown_pct:.2f}%` | Profit Factor: `{ts.profit_factor:.2f}` | Payoff: `{ts.payoff_ratio:.2f}`")
                    lines.append(f"  Expectancy: `{ts.expectancy_r:+.2f}R` (`${ts.expectancy_usd:+,.2f}`)")
                    lines.append("")
            except Exception as e:
                logger.debug(f"Tearsheet in weekly report failed: {e}")

            lines.extend([
                f"*System Performance:*",
                f"  Cycles completed: {cycles}",
                f"  Avg cost per cycle: `${avg_cost_q:.4f}`" if avg_cost_q else "  Avg cost: N/A",
            ])
            
            if tok_result:
                lines.append("\n*Token Usage:*")
                for row in tok_result:
                    lines.append(f"  {row.provider.upper()}: {row.total:,} tokens")
            
            if closed:
                lines.append("\n*Trade Breakdown by Asset:*")
                by_symbol = {}
                for p in closed:
                    if p.symbol not in by_symbol:
                        by_symbol[p.symbol] = {"pnl": 0, "count": 0}
                    by_symbol[p.symbol]["pnl"] += p.pnl or 0
                    by_symbol[p.symbol]["count"] += 1
                for sym, data in sorted(by_symbol.items(), key=lambda x: x[1]["pnl"], reverse=True):
                    lines.append(f"  {sym}: {data['count']} trades, `{'${:+.2f}'.format(data['pnl'])}`")
            try:
                from utils.analytics.analysis_tracker import compute_model_source_performance
                async with get_session() as src_session:
                    source_perf = await compute_model_source_performance(src_session, days_back=7)
                if source_perf.get('by_decision_source'):
                    lines.append('\n*Performance by Decision Source (Model):*')
                    for source, data in sorted(source_perf['by_decision_source'].items(), key=lambda x: x[1]['win_rate'], reverse=True):
                        lines.append(f"  {source}: {data['win_rate']}% WR ({data['trades']} trades, avg {data['avg_pnl_pct']:+.3f}%)")
            except Exception as e:
                logger.debug(f'Decision-source performance section failed: {e}')
            
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error generating report: {e}"


# ---------------------------------------------------------------------------
# Backward-compat alias (used by existing main.py references)
# ---------------------------------------------------------------------------
TelegramController = TelegramBot
