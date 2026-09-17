# ==============================================================================
# File: telegram_bot/voice_handler.py
# ==============================================================================

"""
Voice memo transcription pipeline.

Uses Gemini multimodal (already in stack) to transcribe voice notes and audio clips,
then routes transcription to ChatAgent as text input.

No new API keys needed — reuses existing GEMINI_API_KEY.
"""

import asyncio
import base64
import logging
import os
from typing import Optional, Any
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("TradingAgent.VoiceHandler")


class VoiceHandler:
    """Handles Telegram voice notes and audio files with Gemini multimodal transcription."""

    def __init__(
        self,
        chat_agent: Optional[Any] = None,
        bot: Optional[Any] = None,
        settings: Optional[dict] = None,
    ):
        self.chat_agent = chat_agent
        self.bot = bot
        self.settings = settings or {}

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming voice note or audio clip."""
        if not update.message:
            return

        # Authorization check
        if self.bot and hasattr(self.bot, "_is_authorized"):
            if not self.bot._is_authorized(update):
                if hasattr(self.bot, "_reject_unauthorized"):
                    await self.bot._reject_unauthorized(update)
                return

        voice = update.message.voice or update.message.audio
        if not voice:
            return

        status_msg = None
        try:
            status_msg = await update.message.reply_text("🎤 Transcribing...")
        except Exception as e:
            logger.debug(f"[VoiceHandler] Failed to send initial transcribing message: {e}")

        try:
            tg_file = await voice.get_file()
            audio_bytes = await tg_file.download_as_bytearray()
            mime_type = getattr(voice, "mime_type", "audio/ogg") or "audio/ogg"

            transcript = await self._transcribe(bytes(audio_bytes), mime_type=mime_type)

            if not transcript or not transcript.strip():
                if status_msg:
                    await status_msg.edit_text("❌ Tidak dapat mengenali suara dalam pesan audio.")
                return

            transcript = transcript.strip()

            # Brief transcription acknowledgment
            ack_text = f"🎤 Heard: \"{transcript}\""
            if status_msg:
                try:
                    await status_msg.edit_text(ack_text)
                except Exception as e:
                    logger.debug(f"[VoiceHandler] Failed to edit status msg: {e}")

            # Route to ChatAgent
            agent = self.chat_agent
            session_id = None
            if self.bot:
                thread_id = getattr(update.message, "message_thread_id", None)
                chat_id = update.effective_chat.id if update.effective_chat else (
                    update.effective_user.id if update.effective_user else 0
                )
                if isinstance(thread_id, int) and hasattr(self.bot, "topic_manager") and self.bot.topic_manager:
                    session_id = await self.bot.topic_manager.get_session_for_topic(chat_id, thread_id)
                    if not session_id:
                        session_id = await self.bot.topic_manager.create_topic_session(
                            chat_id, thread_id, topic_name=f"Topic-{thread_id}"
                        )
                    agent_key = session_id
                else:
                    agent_key = update.effective_user.id if update.effective_user else chat_id

                if hasattr(self.bot, "_chat_agents"):
                    if agent_key not in self.bot._chat_agents:
                        from telegram_bot.chat_agent import ChatAgent
                        self.bot._chat_agents[agent_key] = ChatAgent(self.bot.settings, agent_key)
                    agent = self.bot._chat_agents[agent_key]
                elif hasattr(self.bot, "chat_agent"):
                    agent = self.bot.chat_agent

            if agent:
                if hasattr(agent, "handle"):
                    is_streaming = False
                    if self.bot and hasattr(self.bot, "settings"):
                        is_streaming = bool(self.bot.settings.get("telegram", {}).get("streaming", False))

                    reply, pending = await agent.handle(
                        update,
                        context,
                        override_text=transcript,
                        session_id=session_id,
                        stream=is_streaming,
                        update=update,
                    )

                    if not is_streaming and reply:
                        from telegram_bot.sanitizer import sanitize_telegram_html
                        from telegram.constants import ParseMode
                        chunks = [reply]
                        if self.bot and hasattr(self.bot, "_chunk_text"):
                            chunks = self.bot._chunk_text(reply)
                        for chunk in chunks:
                            try:
                                formatted = sanitize_telegram_html(chunk)
                                await update.message.reply_text(formatted, parse_mode=ParseMode.HTML)
                            except Exception:
                                await update.message.reply_text(chunk)

                    if hasattr(agent, "pop_pending_charts"):
                        charts = agent.pop_pending_charts()
                        for chart_buf in charts:
                            try:
                                await update.message.reply_photo(photo=chart_buf)
                            except Exception as e:
                                logger.warning(f"[VoiceHandler] Failed sending chart photo: {e}")

                    if pending:
                        from telegram_bot.command_router import CommandRouter
                        from telegram.constants import ParseMode
                        keyboard = CommandRouter.build_confirm_keyboard(pending.action_id)
                        await update.message.reply_text(
                            f"*AI Mengusulkan Tindakan:*\n\n{pending.description}\n\n"
                            f"_Berlaku selama 90 detik._",
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=keyboard,
                        )
            elif self.bot and hasattr(self.bot, "_handle_chat"):
                update.message.text = transcript
                await self.bot._handle_chat(update, context)

        except Exception as e:
            logger.error(f"[VoiceHandler] Error handling voice memo: {e}", exc_info=True)
            if status_msg:
                try:
                    await status_msg.edit_text(f"❌ Transkripsi gagal: {e}")
                except Exception:
                    pass

    async def _transcribe(self, audio: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribe audio bytes using Gemini multimodal."""
        prompt = "Transcribe this audio accurately. Return only the transcription text, nothing else."

        # 1. Try via LLM provider factory
        try:
            from analysis.providers.llm_factory import get_client_for_task
            client = get_client_for_task("chat_telegram", self.settings)
        except Exception:
            client = None

        if client:
            client_any: Any = client
            if hasattr(client, "transcribe_audio"):
                try:
                    res = await client_any.transcribe_audio(audio, mime_type=mime_type)
                    if res:
                        return str(res).strip()
                except Exception as e:
                    logger.debug(f"[VoiceHandler] transcribe_audio failed: {e}")

            if hasattr(client, "generate_content"):
                try:
                    res = await client_any.generate_content(
                        system_prompt="You are an expert audio transcription assistant. Output ONLY the transcription of the speech.",
                        user_message=prompt,
                        audio_data={"mime_type": mime_type, "data": audio},
                    )
                    if res:
                        return getattr(res, "text", str(res)).strip()
                except Exception as e:
                    logger.debug(f"[VoiceHandler] client.generate_content failed: {e}")

        # 2. Direct HTTP call to Gemini API using GEMINI_API_KEY or settings
        api_key = (
            self.settings.get("api_keys", {}).get("gemini")
            or os.getenv("GEMINI_API_KEY")
        )
        if not api_key:
            keys = os.getenv("GEMINI_API_KEYS", "")
            if keys:
                api_key = keys.split(",")[0].strip()

        if api_key:
            try:
                import aiohttp
                b64_audio = base64.b64encode(audio).decode("utf-8") if isinstance(audio, (bytes, bytearray)) else audio
                chat_role = self.settings.get("llm", {}).get("task_roles", {}).get("chat_telegram", {})
                model_name = chat_role.get("primary") or chat_role.get("model", "gemini-3.5-flash-lite")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                headers = {
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                }
                payload = {
                    "contents": [{
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": b64_audio,
                                }
                            }
                        ]
                    }]
                }
                async with aiohttp.ClientSession() as http_session:
                    async with http_session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                text = "".join(p.get("text", "") for p in parts)
                                if text:
                                    return text.strip()
                        else:
                            err_body = await resp.text()
                            logger.warning(f"[VoiceHandler] Direct Gemini transcription status {resp.status}: {err_body}")
            except Exception as e:
                logger.warning(f"[VoiceHandler] Direct Gemini transcription failed: {e}")

        return ""
