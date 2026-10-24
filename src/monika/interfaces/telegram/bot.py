# ==============================================================================
# File: interfaces/telegram/bot.py
# ==============================================================================

"""
Telegram Bot Interface for Monika.
Main coordinator running commands, voice notes, media processing, interactive callbacks,
and background notification queues with unbypassable administrative security gates.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from monika.interfaces.telegram.base import _TelegramBotMixinBase
from monika.interfaces.telegram.chat_agent import ChatAgent
from monika.interfaces.telegram.command_router import CommandRouter
from monika.interfaces.telegram.formatters.text_builders import TelegramFormatterMixin
from monika.interfaces.telegram.handlers.admin_commands import TelegramAdminCommandsMixin
from monika.interfaces.telegram.handlers.callback_handler import TelegramCallbackHandlerMixin
from monika.interfaces.telegram.handlers.market_commands import TelegramMarketCommandsMixin
from monika.interfaces.telegram.handlers.media_handlers import TelegramMediaHandlerMixin
from monika.interfaces.telegram.handlers.system_commands import TelegramSystemCommandsMixin
from monika.interfaces.telegram.handlers.trading_commands import TelegramTradingCommandsMixin
from monika.interfaces.telegram.sanitizer import sanitize_telegram_html
from monika.interfaces.telegram.topic_manager import TopicManager
from monika.interfaces.telegram.voice_handler import VoiceHandler

logger = logging.getLogger(__name__)


class IgnoreNetworkErrorFilter(logging.Filter):
    def filter(self, record):
        if record.exc_info:
            err_type = str(record.exc_info[0])
            err_msg = str(record.exc_info[1])
            if "NetworkError" in err_type or "Bad Gateway" in err_msg:
                return False
        return True


class TelegramBot(
    TelegramFormatterMixin,
    TelegramCallbackHandlerMixin,
    TelegramMediaHandlerMixin,
    TelegramTradingCommandsMixin,
    TelegramMarketCommandsMixin,
    TelegramSystemCommandsMixin,
    TelegramAdminCommandsMixin,
):
    """
    Main Telegram Bot Controller.
    Composes formatters, command handlers, and media/callback mixins into a single coherent interface.
    """

    def __init__(
        self,
        settings: dict,
        execution_service=None,
        cycle_scheduler=None,
    ):
        self.settings = settings
        self.execution_service = execution_service
        self.cycle_scheduler = cycle_scheduler
        self._activity_log: Optional[Any] = None
        self.task_registry: Optional[Any] = None

        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
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
        from monika.interfaces.telegram.chat_agent import ChatAgent
        from monika.interfaces.telegram.topic_manager import TopicManager
        from monika.interfaces.telegram.voice_handler import VoiceHandler

        self._chat_agents: dict[Any, ChatAgent] = {}
        self.topic_manager = TopicManager()
        self.voice_handler = VoiceHandler(bot=self, settings=self.settings)

        from monika.interfaces.telegram.command_router import CommandRouter

        self._router = CommandRouter(
            admin_chat_id=self.admin_chat_id,
            allowed_user_ids=self.allowed_user_ids,
        )

        self._is_running: bool = False
        self._outbound_queue: asyncio.Queue = asyncio.Queue()
        self._outbound_worker_task: Optional[asyncio.Task] = None
        self._last_send_global: float = 0.0
        self._last_send_per_chat: dict[int, float] = {}
        self._offline_queue_file: str = os.path.join("data", "telegram_offline_queue.jsonl")
        self._background_tasks: set[asyncio.Task[Any]] = set()

        if not self.token or self.token.startswith("your_"):
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot will not connect")
            self._app = None
        else:
            self._app = ApplicationBuilder().token(self.token).build()
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
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("positions", self._cmd_positions))
        app.add_handler(CommandHandler("brief", self._cmd_brief))
        app.add_handler(CommandHandler("analysis", self._cmd_analysis))
        app.add_handler(CommandHandler("pipeline", self._cmd_pipeline))
        app.add_handler(CommandHandler("history", self._cmd_history))
        app.add_handler(CommandHandler("risk", self._cmd_risk))
        app.add_handler(CommandHandler("vix", self._cmd_vix))
        app.add_handler(CommandHandler("tokens", self._cmd_tokens))
        app.add_handler(CommandHandler("report", self._cmd_report))
        app.add_handler(CommandHandler("tearsheet", self._cmd_tearsheet))
        app.add_handler(CommandHandler("stats", self._cmd_stats))
        app.add_handler(CommandHandler("cost", self._cmd_cost))
        app.add_handler(CommandHandler("credits", self._cmd_credits))
        app.add_handler(CommandHandler("edge", self._cmd_edge))
        app.add_handler(CommandHandler("calibration", self._cmd_calibration))
        app.add_handler(CommandHandler("intel", self._cmd_intel))
        app.add_handler(CommandHandler("archive_intel", self._cmd_archive_intel))
        app.add_handler(CommandHandler("regime", self._cmd_regime))
        app.add_handler(CommandHandler("audit", self._cmd_audit))
        app.add_handler(CommandHandler("pause", self._cmd_pause))
        app.add_handler(CommandHandler("resume", self._cmd_resume))
        app.add_handler(CommandHandler("suspend", self._cmd_suspend))
        app.add_handler(CommandHandler("unsuspend", self._cmd_unsuspend))
        app.add_handler(CommandHandler("kill", self._cmd_kill))
        app.add_handler(CommandHandler("emergency", self._cmd_emergency))
        app.add_handler(CommandHandler("close", self._cmd_close))
        app.add_handler(CommandHandler("closeall", self._cmd_closeall))
        app.add_handler(CommandHandler("override", self._cmd_override))
        app.add_handler(CommandHandler("run", self._cmd_run))
        app.add_handler(CommandHandler("backtest", self._cmd_backtest))
        app.add_handler(CommandHandler("approve", self._cmd_approve))
        app.add_handler(CommandHandler("reject", self._cmd_reject))
        app.add_handler(CommandHandler("steer", self._cmd_steer))
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
        app.add_handler(CommandHandler("risk_deep", self._cmd_risk_deep))
        app.add_handler(CommandHandler("approvals", self._cmd_approvals))
        app.add_handler(CommandHandler("trailing", self._cmd_trailing))
        app.add_handler(CommandHandler("reconcile", self._cmd_reconcile))
        app.add_handler(CommandHandler("fedwatch", self._cmd_fedwatch))
        app.add_handler(CommandHandler("yields", self._cmd_yields))
        app.add_handler(CommandHandler("macro_weekly", self._cmd_macro_weekly))
        app.add_handler(CommandHandler("weekly_macro", self._cmd_macro_weekly))
        app.add_handler(CommandHandler("fear_greed", self._cmd_fear_greed))
        app.add_handler(CommandHandler("cot", self._cmd_cot))
        app.add_handler(CommandHandler("playbooks", self._cmd_playbooks))
        app.add_handler(CommandHandler("rollback", self._cmd_rollback))
        app.add_handler(CommandHandler("crystallized", self._cmd_crystallized))
        app.add_handler(CommandHandler("cron", self._cmd_cron))
        app.add_handler(CommandHandler("counterfactual", self._cmd_counterfactual))
        app.add_handler(CommandHandler("chronicle", self._cmd_chronicle))
        app.add_handler(CommandHandler("monte_carlo", self._cmd_monte_carlo))
        app.add_handler(CommandHandler("montecarlo", self._cmd_monte_carlo))
        app.add_handler(CommandHandler("export_chat", self._cmd_export_chat))
        app.add_handler(CommandHandler("export", self._cmd_export_chat))
        app.add_handler(CommandHandler("undo", self._cmd_undo))
        app.add_handler(CommandHandler("backup", self._cmd_backup))
        app.add_handler(CommandHandler("stress_test", self._cmd_stress_test))
        app.add_handler(CommandHandler("stresstest", self._cmd_stress_test))
        app.add_handler(CommandHandler("model", self._cmd_model))
        app.add_handler(CommandHandler("pair", self._cmd_pair))
        app.add_handler(CommandHandler("cancel", self._cmd_cancel))
        app.add_handler(CommandHandler("account", self._cmd_account))
        app.add_handler(CommandHandler("tasks", self._cmd_tasks))
        app.add_handler(CommandHandler("debate", self._cmd_debate))
        app.add_handler(CommandHandler("chart", self._cmd_chart))
        app.add_handler(CommandHandler("smc", self._cmd_smc))
        app.add_handler(CommandHandler("orders", self._cmd_orders))
        app.add_handler(CommandHandler("factors", self._cmd_factors))
        app.add_handler(CommandHandler("alpha", self._cmd_alpha))
        # Model override commands → routed to chat with prefix intact
        for cmd in ("fast", "quick", "medium", "mid", "analyze", "analisis", "research"):
            app.add_handler(CommandHandler(cmd, self._handle_chat))
        # Callback queries (inline keyboards)
        app.add_handler(CallbackQueryHandler(self._handle_callback))
        # Free-text → AI chat
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_chat))
        # Photo / Image Vision → AI chat
        app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))
        # Document (PDF) auto-extraction → AI chat
        app.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))
        # Voice memo & audio transcription
        if hasattr(self, "voice_handler") and self.voice_handler:
            app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.voice_handler.handle_voice))
        # Unknown slash command fallback with fuzzy suggestion
        app.add_handler(MessageHandler(filters.COMMAND, self._handle_unknown_command))
        # Centralized error handler
        app.add_error_handler(self._on_telegram_error)

    async def _on_telegram_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Centralized Telegram error handler with Conflict backoff recovery."""
        error = context.error
        if error is None:
            return
        try:
            from telegram.error import Conflict, NetworkError, TimedOut

            if isinstance(error, Conflict):
                logger.warning(
                    f"[TelegramBot] Conflict detected (another instance running with same token): {error}. "
                    "Backing off for 15 seconds to prevent polling churn."
                )
                await asyncio.sleep(15.0)
                return
            elif isinstance(error, (NetworkError, TimedOut)):
                logger.debug(f"[TelegramBot] Transient network/timeout error: {error}")
                return
        except Exception:
            pass
        logger.error(f"[TelegramBot] Unhandled error: {error}", exc_info=error)

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
            try:
                from telegram import BotCommand

                commands = [
                    BotCommand("status", "Show agent and portfolio status"),
                    BotCommand("positions", "List open trading positions"),
                    BotCommand("brief", "Latest market intelligence macro brief"),
                    BotCommand("edge", "Statistical edge and win rate assessment"),
                    BotCommand("risk", "Current risk state and limits"),
                    BotCommand("vix", "CBOE VIX volatility gauge"),
                    BotCommand("history", "Recent trade history"),
                    BotCommand("help", "Help and command manual"),
                ]
                await self._app.bot.set_my_commands(commands)
            except Exception as e:
                logger.debug(f"Failed to set bot commands: {e}")

            self._is_running = True
            self._outbound_worker_task = asyncio.create_task(self._process_outbound_queue())
            await self._flush_offline_queue()
            logger.info(f"Telegram Bot online. Admin: {self.admin_chat_id}")

            # Block until cancelled
            await asyncio.get_running_loop().create_future()
        except asyncio.CancelledError:
            logger.info("Stopping Telegram Bot...")
        finally:
            self._is_running = False
            if self._outbound_worker_task and not self._outbound_worker_task.done():
                self._outbound_worker_task.cancel()
                try:
                    await self._outbound_worker_task
                except asyncio.CancelledError, Exception:
                    pass
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
        if self._outbound_worker_task and not self._outbound_worker_task.done():
            self._outbound_worker_task.cancel()
            try:
                await self._outbound_worker_task
            except asyncio.CancelledError, Exception:
                pass
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

    async def _process_outbound_queue(self) -> None:
        """Background worker consuming outbound queue with token-bucket rate limiter and RetryAfter backoff."""
        from telegram.error import RetryAfter

        while self._is_running:
            try:
                item = await self._outbound_queue.get()
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)
                continue

            chat_id = item.get("chat_id")
            text = item.get("text", "")
            raw_text = item.get("raw_text", text)
            parse_mode = item.get("parse_mode")
            extra_kwargs = item.get("extra_kwargs", {})
            is_critical = item.get("is_critical", False)

            # Global rate limit: 25 msgs/sec -> min interval 0.04s
            now = time.time()
            global_delta = now - self._last_send_global
            if global_delta < 0.04:
                await asyncio.sleep(0.04 - global_delta)

            # Per-chat rate limit: 1 msg/sec -> min interval 1.0s (bypassed for critical alerts)
            if chat_id is not None and not is_critical:
                chat_delta = time.time() - self._last_send_per_chat.get(chat_id, 0.0)
                if chat_delta < 1.0:
                    await asyncio.sleep(1.0 - chat_delta)

            try:
                if self._app and self._app.bot and chat_id is not None:
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=parse_mode,
                        **extra_kwargs,
                    )
                    self._last_send_global = time.time()
                    self._last_send_per_chat[chat_id] = time.time()
            except RetryAfter as ra:
                raw_retry = getattr(ra, "retry_after", 1.0)
                if isinstance(raw_retry, timedelta):
                    retry_seconds = float(raw_retry.total_seconds())
                else:
                    try:
                        retry_seconds = float(raw_retry)
                    except TypeError, ValueError:
                        retry_seconds = 1.0
                logger.warning(f"[TelegramOutbound] FloodControl RetryAfter({retry_seconds}s). Pausing queue...")
                if is_critical:
                    self._save_to_offline_buffer(item)
                await asyncio.sleep(retry_seconds + 0.1)
                if not is_critical:
                    await self._outbound_queue.put(item)
            except Exception as send_err:
                if "can't parse entities" in str(send_err).lower() or "parsing entity" in str(send_err).lower():
                    try:
                        if self._app and self._app.bot and chat_id is not None:
                            await self._app.bot.send_message(
                                chat_id=chat_id,
                                text=raw_text,
                                parse_mode=None,
                                **extra_kwargs,
                            )
                            self._last_send_global = time.time()
                            self._last_send_per_chat[chat_id] = time.time()
                    except Exception as plain_err:
                        logger.error(f"[TelegramOutbound] Plain text retry failed: {plain_err}")
                        if is_critical:
                            self._save_to_offline_buffer(item)
                else:
                    logger.error(f"[TelegramOutbound] Failed to send message to {chat_id}: {send_err}")
                    if is_critical:
                        self._save_to_offline_buffer(item)
            finally:
                self._outbound_queue.task_done()

    def _save_to_offline_buffer(self, item: dict) -> None:
        """Persist unsent critical alerts to disk buffer during network drop."""
        try:
            os.makedirs(os.path.dirname(self._offline_queue_file), exist_ok=True)
            with open(self._offline_queue_file, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "chat_id": item.get("chat_id"),
                            "text": item.get("raw_text") or item.get("text"),
                            "parse_mode": item.get("parse_mode"),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    + "\n"
                )
            logger.critical(f"[TelegramOutbound] Critical alert saved to offline buffer ({self._offline_queue_file})")
        except Exception as disk_err:
            logger.error(f"[TelegramOutbound] Failed to write offline buffer: {disk_err}")

    async def _flush_offline_queue(self) -> None:
        """Drain and send cached offline alerts once Telegram connection restores."""
        if not os.path.exists(self._offline_queue_file):
            return
        try:
            with open(self._offline_queue_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            if not lines:
                return
            logger.info(f"[TelegramOutbound] Flushing {len(lines)} offline buffered messages...")
            for line in lines:
                try:
                    entry = json.loads(line)
                    await self._outbound_queue.put(
                        {
                            "chat_id": entry.get("chat_id") or self.admin_chat_id,
                            "text": f"⚠️ [RECOVERED OFFLINE ALERT - {entry.get('timestamp')}]\n\n{entry.get('text')}",
                            "raw_text": entry.get("text"),
                            "parse_mode": None,
                            "is_critical": False,
                        }
                    )
                except Exception:
                    pass
            os.remove(self._offline_queue_file)
        except Exception as flush_err:
            logger.error(f"[TelegramOutbound] Error flushing offline queue: {flush_err}")

    async def send_notification(
        self,
        text: str,
        parse_mode: str = ParseMode.HTML,
        message_thread_id: Optional[int] = None,
        is_critical: bool = False,
        chat_id: Optional[int] = None,
    ) -> None:
        """Mengirim pesan notifikasi ke admin atau chat spesifik melalui outbound queue."""
        target_chat_id = chat_id or self.admin_chat_id
        critical_alert = is_critical or any(
            k in text for k in ("RiskGate", "KILL", "DARURAT", "EMERGENCY", "Breach", "Liquidation", "DRAWDOW")
        )
        if not self._app or not target_chat_id or not self._is_running:
            if critical_alert and target_chat_id:
                self._save_to_offline_buffer(
                    {
                        "chat_id": target_chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "message_thread_id": message_thread_id,
                        "is_critical": True,
                        "enqueued_at": time.time(),
                    }
                )
            return

        is_html = parse_mode == ParseMode.HTML
        chunks = self._chunk_text(text, max_len=4000, sanitize_format=False, is_html=is_html)

        for chunk in chunks:
            if not self._is_running:
                return
            extra_kwargs = {}
            if message_thread_id is not None:
                extra_kwargs["message_thread_id"] = message_thread_id
            formatted_chunk = sanitize_telegram_html(chunk) if parse_mode == ParseMode.HTML else chunk

            if (
                hasattr(self, "_outbound_queue")
                and self._outbound_queue is not None
                and self._outbound_worker_task is not None
                and not self._outbound_worker_task.done()
            ):
                await self._outbound_queue.put(
                    {
                        "chat_id": target_chat_id,
                        "text": formatted_chunk,
                        "raw_text": chunk,
                        "parse_mode": parse_mode,
                        "extra_kwargs": extra_kwargs,
                        "is_critical": critical_alert,
                    }
                )
            else:
                try:
                    await self._app.bot.send_message(
                        chat_id=target_chat_id,
                        text=formatted_chunk,
                        parse_mode=parse_mode,
                        **extra_kwargs,
                    )
                except Exception as e:
                    logger.warning(f"Direct send notification failed: {e}")
                    if critical_alert:
                        self._save_to_offline_buffer(
                            {
                                "chat_id": target_chat_id,
                                "text": formatted_chunk,
                                "raw_text": chunk,
                                "parse_mode": parse_mode,
                            }
                        )

    async def request_fallback_consent(self, prompt_text: str, tg_event: asyncio.Event, tg_result: dict) -> None:
        """Mengirim notifikasi inline keyboard untuk fallback consent ke admin."""
        if not self._app or not self.admin_chat_id:
            return

        import uuid

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        fallback_id = str(uuid.uuid4())[:8]

        # Simpan state untuk di-resolve oleh _handle_callback
        if not hasattr(self, "_fallback_events"):
            self._fallback_events = {}
            self._fallback_results = {}

        self._fallback_events[fallback_id] = tg_event
        self._fallback_results[fallback_id] = tg_result

        keyboard = [
            [InlineKeyboardButton("[ SATU SIKLUS ]", callback_data=f"fallback:once:{fallback_id}")],
            [InlineKeyboardButton("[ SETERUSNYA ]", callback_data=f"fallback:always:{fallback_id}")],
            [InlineKeyboardButton("[ TOLAK ]", callback_data=f"fallback:reject:{fallback_id}")],
        ]

        try:
            await self._app.bot.send_message(
                chat_id=self.admin_chat_id,
                text=f"[ PERINGATAN: FALLBACK DIPERLUKAN ]\n\n{prompt_text}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"Fallback consent prompt failed: {e}")

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
            await update.message.reply_text("[AKSES DITOLAK] Perintah ini hanya untuk admin.")
        elif update.effective_message:
            await update.effective_message.reply_text("[AKSES DITOLAK] Perintah ini hanya untuk admin.")

    async def _handle_unknown_command(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unrecognized slash commands with fuzzy matching and recommendations."""
        if not update.message or not update.message.text:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        raw_cmd = update.message.text.split()[0].lstrip("/")
        from monika.interfaces.telegram.fuzzy_router import FuzzyCommandRouter

        router = FuzzyCommandRouter()
        matched_def, suggestions = router.resolve(raw_cmd)

        if matched_def:
            keyboard = [
                [InlineKeyboardButton(f"▶ Run /{matched_def.command}", callback_data=f"cmd:{matched_def.command}")]
            ]
            await update.message.reply_text(
                f"[?] Unknown command `/{raw_cmd}`.\n\nDid you mean: *{matched_def.usage}*?\n_{matched_def.description}_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        elif suggestions:
            suggest_str = ", ".join(f"`{s}`" for s in suggestions)
            keyboard = [[InlineKeyboardButton(s, callback_data=f"cmd:{s.lstrip('/')}") for s in suggestions[:3]]]
            await update.message.reply_text(
                f"[?] Unknown command `/{raw_cmd}`.\n\nDid you mean: {suggest_str}?\nType `/help` to see all available commands.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await update.message.reply_text(
                f"[?] Unknown command `/{raw_cmd}`. Type `/help` to see all available commands.",
                parse_mode=ParseMode.MARKDOWN,
            )

    async def _monitor_pending_expiry(self, msg: Any, action_id: str, agent: Any, timeout: float = 90.0) -> None:
        """Monitors pending action expiration and revokes inline keyboard after timeout."""
        try:
            await asyncio.sleep(timeout)
            action = await agent.get_pending_action(action_id)
            if action and not getattr(action, "is_confirmed", False):
                agent._pending_actions.pop(action_id, None)
                await agent._delete_persisted_pending_action(action_id)
                try:
                    await msg.edit_text(
                        f"⏱️ <b>[EXPIRED] Usulan Tindakan #{action_id}</b>\n\n"
                        f"<s>{html.escape(action.description)}</s>\n\n"
                        f"<i>Batas waktu konfirmasi 90 detik telah berakhir. Keyboard dicabut demi keselamatan finansial.</i>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=None,
                    )
                except Exception as edit_err:
                    logger.debug(f"[Bot] Could not edit expired action msg: {edit_err}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[Bot] Pending expiry monitor error: {e}")


# ---------------------------------------------------------------------------
# Backward-compat alias (used by existing main.py references)
# ---------------------------------------------------------------------------
TelegramController = TelegramBot

__all__ = ["TelegramBot", "TelegramController"]
