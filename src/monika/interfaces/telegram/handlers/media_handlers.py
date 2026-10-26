# ==============================================================================
# File: interfaces/telegram/handlers/media_handlers.py
# ==============================================================================

"""
Media, document, photo, and conversational chat handlers mixin for Telegram bot.
Handles incoming voice, audio, photos, documents, and chat interaction routing.
"""

from __future__ import annotations

import asyncio
import html
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.base import _TelegramBotMixinBase
from monika.interfaces.telegram.chat_agent import ChatAgent
from monika.interfaces.telegram.command_router import CommandRouter
from monika.interfaces.telegram.sanitizer import sanitize_telegram_html

logger = logging.getLogger(__name__)


class TelegramMediaHandlerMixin(_TelegramBotMixinBase):
    """Mixin providing chat and media handling methods for TelegramBot."""

    async def _handle_chat(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return
        if not self._is_authorized(update) or not update.effective_user:
            return await self._reject_unauthorized(update)

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if update.effective_chat else user_id
        user_msg = str(update.message.text).strip() if update.message and update.message.text else ""

        # Check emergency close all fast-path
        if user_msg and re.search(r"(?i)\b(close\s*all|tutup\s*semua|emergency\s*close|likuidasi\s*semua)\b", user_msg):
            return await self._cmd_closeall(update, ctx)

        # Prune old chat agents
        now = datetime.now(timezone.utc)
        to_delete = []
        for uid, agent in self._chat_agents.items():
            has_active_approval = any(exp > now for exp in getattr(agent, "_session_approvals", {}).values())
            ttl = 14400 if has_active_approval else 3600
            if agent.last_active is not None and (now - agent.last_active).total_seconds() > ttl:
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
            from monika.interfaces.telegram.chat_agent import ChatAgent

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
        was_streamed = getattr(agent, "was_last_turn_streamed", False) is True
        if not was_streamed and reply:
            for chunk in self._chunk_text(reply):
                try:
                    formatted_chunk = sanitize_telegram_html(chunk)
                    await update.message.reply_text(formatted_chunk, parse_mode=ParseMode.HTML)
                except Exception as e:
                    err_msg = str(e).lower()
                    if "timed out" in err_msg or "timeout" in err_msg:
                        logger.warning(
                            f"Telegram chunk send timed out ({e}). Retrying plain text with extended timeout..."
                        )
                        try:
                            await update.message.reply_text(chunk, read_timeout=35.0, write_timeout=35.0)
                        except Exception as retry_err:
                            logger.error(f"Failed sending chunk after timeout retry: {retry_err}")
                    else:
                        logger.warning(f"Failed to send HTML reply chunk, falling back to plain text: {e}")
                        await update.message.reply_text(chunk)

        # Send any generated chart images
        if hasattr(agent, "pop_pending_charts"):
            charts = agent.pop_pending_charts()
            for chart_buf in charts:
                try:
                    await update.message.reply_photo(photo=chart_buf)
                except Exception as e:
                    logger.warning(f"Failed sending chart photo to user {user_id}: {e}")

        # Send any generated files / documents
        if hasattr(agent, "pop_pending_files"):
            files = agent.pop_pending_files()
            for filename, file_buf in files:
                try:
                    file_buf.seek(0)
                    await update.message.reply_document(document=file_buf, filename=filename)
                except Exception as e:
                    logger.warning(f"Failed sending document {filename} to user {user_id}: {e}")

        # If AI proposed an action, send confirm keyboard with live expiry monitor
        if pending:
            from monika.interfaces.telegram.command_router import CommandRouter

            keyboard = CommandRouter.build_confirm_keyboard(pending.action_id)
            prop_text = (
                f"<b>AI Mengusulkan Tindakan:</b>\n\n"
                f"{html.escape(pending.description)}\n\n"
                f"<i>Berlaku selama 90 detik (hitung mundur otomatis).</i>"
            )
            sent_prop = await update.message.reply_text(
                prop_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            asyncio.create_task(self._monitor_pending_expiry(sent_prop, pending.action_id, agent, timeout=90.0))

    async def _handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming image/photo from user for multimodal vision analysis."""
        if not update.message or not update.message.photo:
            return
        if not self._is_authorized(update) or not update.effective_user:
            return await self._reject_unauthorized(update)

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if update.effective_chat else user_id
        caption = (update.message.caption or "").strip() or "Tolong analisa gambar/chart ini secara teknikal dan SMC."

        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        buf = io.BytesIO()
        await photo_file.download_to_memory(buf)
        image_bytes = buf.getvalue()

        now = datetime.now(timezone.utc)
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

        if update.message.chat:
            try:
                res = update.message.chat.send_action(ChatAction.TYPING)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        is_admin_user = self._is_admin(update)
        if agent_key not in self._chat_agents:
            from monika.interfaces.telegram.chat_agent import ChatAgent

            self._chat_agents[agent_key] = ChatAgent(self.settings, agent_key, is_admin=is_admin_user)

        agent = self._chat_agents[agent_key]
        agent.is_admin = is_admin_user
        agent.last_active = now

        chat_obj = update.message.chat

        async def _typing_cb():
            if chat_obj:
                await chat_obj.send_action(ChatAction.TYPING)

        try:
            reply, pending = await agent.handle(
                caption,
                context=ctx,
                typing_callback=_typing_cb,
                session_id=session_id,
                stream=False,
                update=update,
                image_bytes=image_bytes,
            )
        except Exception as e:
            logger.error(f"ChatAgent error handling photo for user {user_id}: {e}")
            await update.message.reply_text(f"[ERROR] {e}")
            return

        if reply:
            for chunk in self._chunk_text(reply):
                try:
                    formatted_chunk = sanitize_telegram_html(chunk)
                    await update.message.reply_text(formatted_chunk, parse_mode=ParseMode.HTML)
                except Exception as e:
                    err_msg = str(e).lower()
                    if "timed out" in err_msg or "timeout" in err_msg:
                        logger.warning(
                            f"Telegram chunk send timed out ({e}). Retrying plain text with extended timeout..."
                        )
                        try:
                            await update.message.reply_text(chunk, read_timeout=35.0, write_timeout=35.0)
                        except Exception as retry_err:
                            logger.error(f"Failed sending chunk after timeout retry: {retry_err}")
                    else:
                        logger.warning(f"Failed to send HTML reply chunk: {e}")
                        await update.message.reply_text(chunk)

        if hasattr(agent, "pop_pending_charts"):
            charts = agent.pop_pending_charts()
            for chart_buf in charts:
                try:
                    await update.message.reply_photo(photo=chart_buf)
                except Exception as e:
                    logger.warning(f"Failed sending chart photo to user {user_id}: {e}")

        if hasattr(agent, "pop_pending_files"):
            files = agent.pop_pending_files()
            for filename, file_buf in files:
                try:
                    file_buf.seek(0)
                    await update.message.reply_document(document=file_buf, filename=filename)
                except Exception as e:
                    logger.warning(f"Failed sending document {filename} to user {user_id}: {e}")

        if pending:
            from monika.interfaces.telegram.command_router import CommandRouter

            keyboard = CommandRouter.build_confirm_keyboard(pending.action_id)
            await update.message.reply_text(
                f"*AI Mengusulkan Tindakan:*\n\n{pending.description}\n\n_Berlaku selama 90 detik._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )

    async def _handle_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming documents (especially PDF reports, economic calendars, transcripts)."""
        if not update.message or not update.message.document:
            return
        if not self._is_authorized(update) or not update.effective_user:
            return await self._reject_unauthorized(update)

        doc = update.message.document
        file_name = doc.file_name or "document"
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if update.effective_chat else user_id
        caption = (update.message.caption or "").strip()

        is_pdf = file_name.lower().endswith(".pdf") or doc.mime_type == "application/pdf"
        if not is_pdf:
            await update.message.reply_text(
                f"Format dokumen '{file_name}' belum didukung untuk auto-parsing (saat ini mendukung file .pdf)."
            )
            return

        try:
            if update.message.chat:
                try:
                    res = update.message.chat.send_action(ChatAction.TYPING)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

            doc_file = await doc.get_file()
            import io

            buf = io.BytesIO()
            await doc_file.download_to_memory(buf)
            buf.seek(0)

            from pypdf import PdfReader

            reader = PdfReader(buf)
            pages_text = []
            for idx, page in enumerate(reader.pages[:25]):
                txt = page.extract_text() or ""
                if txt.strip():
                    pages_text.append(f"[Halaman {idx + 1}]\n{txt.strip()}")

            extracted_content = "\n\n".join(pages_text)
            if not extracted_content.strip():
                await update.message.reply_text(
                    "Dokumen PDF berhasil diterima tetapi teks tidak dapat diekstrak (kemungkinan scanned/image-only PDF)."
                )
                return

            user_prompt = f"User mengunggah dokumen PDF: '{file_name}' ({len(reader.pages)} halaman).\n\n"
            if caption:
                user_prompt += f"Instruksi user: {caption}\n\n"
            else:
                user_prompt += "Tolong rangkum dan analisa poin-poin penting dari isi dokumen PDF ini untuk konteks pasar dan trading:\n\n"
            user_prompt += f"--- ISI DOKUMEN ---\n{extracted_content[:12000]}"

            now = datetime.now(timezone.utc)
            thread_id = update.message.message_thread_id
            session_id = f"{chat_id}_{thread_id}" if thread_id else str(chat_id)
            agent_key = f"{user_id}_{thread_id}" if thread_id else str(user_id)

            is_admin_user = self._is_admin(update)
            if agent_key not in self._chat_agents:
                from monika.interfaces.telegram.chat_agent import ChatAgent

                self._chat_agents[agent_key] = ChatAgent(self.settings, agent_key, is_admin=is_admin_user)

            agent = self._chat_agents[agent_key]
            agent.is_admin = is_admin_user
            agent.last_active = now

            chat_obj = update.message.chat

            async def _typing_cb():
                if chat_obj:
                    await chat_obj.send_action(ChatAction.TYPING)

            reply, pending = await agent.handle(
                user_prompt,
                context=ctx,
                typing_callback=_typing_cb,
                session_id=session_id,
                stream=False,
                update=update,
            )

            if reply:
                for chunk in self._chunk_text(reply):
                    try:
                        formatted_chunk = sanitize_telegram_html(chunk)
                        await update.message.reply_text(formatted_chunk, parse_mode=ParseMode.HTML)
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "timed out" in err_msg or "timeout" in err_msg:
                            logger.warning(
                                f"Telegram chunk send timed out ({e}). Retrying plain text with extended timeout..."
                            )
                            try:
                                await update.message.reply_text(chunk, read_timeout=35.0, write_timeout=35.0)
                            except Exception as retry_err:
                                logger.error(f"Failed sending chunk after timeout retry: {retry_err}")
                        else:
                            logger.warning(f"Failed to send HTML reply chunk: {e}")
                            await update.message.reply_text(chunk)

            if hasattr(agent, "pop_pending_charts"):
                charts = agent.pop_pending_charts()
                for chart_buf in charts:
                    try:
                        await update.message.reply_photo(photo=chart_buf)
                    except Exception as e:
                        logger.warning(f"Failed sending chart photo to user {user_id}: {e}")

            if hasattr(agent, "pop_pending_files"):
                files = agent.pop_pending_files()
                for fn, file_buf in files:
                    try:
                        file_buf.seek(0)
                        await update.message.reply_document(document=file_buf, filename=fn)
                    except Exception as e:
                        logger.warning(f"Failed sending document {fn} to user {user_id}: {e}")

            if pending:
                from monika.interfaces.telegram.command_router import CommandRouter

                keyboard = CommandRouter.build_confirm_keyboard(pending.action_id)
                await update.message.reply_text(
                    f"*AI Mengusulkan Tindakan:*\n\n{pending.description}\n\n_Berlaku selama 90 detik._",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                )
        except Exception as e:
            logger.error(f"ChatAgent error handling PDF document for user {user_id}: {e}", exc_info=True)
            await update.message.reply_text(f"[ERROR] Gagal memproses dokumen PDF: {e}")

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
            from monika.interfaces.telegram.chat_agent import ChatAgent

            is_adm = self._router.is_admin(user_id) if hasattr(self._router, "is_admin") else False
            candidate = ChatAgent(self.settings, user_id, is_admin=is_adm)
            persisted = await candidate.get_pending_action(action_id)
            if persisted:
                agent = candidate
                self._chat_agents[user_id] = agent
        return agent


__all__ = ["TelegramMediaHandlerMixin"]
