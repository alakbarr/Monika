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
            status_msg = await update.message.reply_text("[PROSES] Mentranskripsikan rekaman suara...")
        except Exception as e:
            logger.debug(f"[VoiceHandler] Failed to send initial transcribing message: {e}")

        try:
            tg_file = await voice.get_file()
            audio_bytes = await tg_file.download_as_bytearray()
            mime_type = getattr(voice, "mime_type", "audio/ogg") or "audio/ogg"

            transcript = await self._transcribe(bytes(audio_bytes), mime_type=mime_type)

            if not transcript or not transcript.strip():
                if status_msg:
                    await status_msg.edit_text("[GAGAL] Tidak dapat mengenali suara dalam pesan audio.")
                return

            transcript = transcript.strip()

            # ── Deterministic Voice Safety Gate ──
            from monika.interfaces.telegram.voice_safety_gate import VoiceSafetyGate
            proposal = VoiceSafetyGate.extract_trade_intent(transcript)
            if proposal.is_trade_command:
                if proposal.error:
                    if status_msg:
                        await status_msg.edit_text(f"[SUARA] \"{transcript}\"\n\n[PERINGATAN] {proposal.error}")
                    return

                from monika.domain.risk.approval_hub import ApprovalHub
                import uuid
                req_id = f"voice_{uuid.uuid4().hex[:8]}"
                hub = ApprovalHub.get_instance()
                req = hub.create_request(
                    request_id=req_id,
                    symbol=proposal.symbol or "UNKNOWN",
                    action=proposal.action or "ORDER",
                    request_type="trade_proposal",
                    details={
                        "lots": proposal.lots,
                        "stop_loss": proposal.stop_loss,
                        "take_profit": proposal.take_profit,
                        "transcript": transcript,
                    },
                    ttl_minutes=3,
                )
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                from telegram.constants import ParseMode
                sl_str = f" | SL: `{proposal.stop_loss}`" if proposal.stop_loss else ""
                tp_str = f" | TP: `{proposal.take_profit}`" if proposal.take_profit else ""
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"[EKSEKUSI] {proposal.action} {proposal.lots} {proposal.symbol}", callback_data=f"confirm:{req_id}"),
                        InlineKeyboardButton("[BATALKAN]", callback_data=f"reject:{req_id}"),
                    ]
                ])
                card_text = (
                    f"*Perintah Suara Terdeteksi*\n"
                    f"• *Transkrip*: \"{transcript}\"\n"
                    f"• *Tindakan*: `{proposal.action}` *{proposal.symbol}*\n"
                    f"• *Volume*: `{proposal.lots} Lot`{sl_str}{tp_str}\n\n"
                    f"*Konfirmasi*: Tekan tombol di bawah untuk menyetujui atau membatalkan eksekusi order."
                )
                if status_msg:
                    await status_msg.edit_text(card_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                else:
                    await update.message.reply_text(card_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                return

            # Brief transcription acknowledgment for conversational text
            ack_text = f"[SUARA] \"{transcript}\""
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
                        from monika.interfaces.telegram.chat_agent import ChatAgent
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
                        from monika.interfaces.telegram.sanitizer import sanitize_telegram_html
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
                        from monika.interfaces.telegram.command_router import CommandRouter
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
                    await status_msg.edit_text(f"[GAGAL] Transkripsi gagal: {e}")
                except Exception:
                    pass

    async def _transcribe(self, audio: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribe audio bytes using Gemini multimodal."""
        prompt = "Transcribe this audio accurately. Return only the transcription text, nothing else."

        # 1. Try via LLM provider factory
        try:
            from monika.infrastructure.providers.llm_factory import get_client_for_task
            task_roles = (self.settings or {}).get("llm", {}).get("task_roles", {})
            if "voice_transcription" in task_roles:
                client = get_client_for_task("voice_transcription", self.settings)
            else:
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

        # 2. Iterate through candidate models across OpenRouter, Groq, and Gemini
        task_roles = (self.settings or {}).get("llm", {}).get("task_roles", {})
        voice_role = task_roles.get("voice_transcription", {})
        candidate_models: list[str] = []
        custom_tg_model = (self.settings or {}).get("telegram", {}).get("voice_transcription_model")
        if custom_tg_model:
            candidate_models.append(custom_tg_model)

        for k in ("primary", "model", "fallback_1", "fallback_2", "fallback_3", "fallback_4"):
            m = voice_role.get(k)
            if m and m not in candidate_models:
                candidate_models.append(m)

        if not candidate_models:
            chat_role = task_roles.get("chat_telegram", {})
            chat_m = chat_role.get("primary") or chat_role.get("model")
            if chat_m:
                candidate_models.append(chat_m)
            for live_m in (
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.5-flash",
            ):
                if live_m not in candidate_models:
                    candidate_models.append(live_m)

        # Resolve API keys
        openrouter_key = (
            self.settings.get("api_keys", {}).get("openrouter")
            or os.getenv("OPENROUTER_API_KEY")
        )
        if not openrouter_key:
            from monika.infrastructure.api.openrouter_rate_limiter import get_paid_key, get_free_keys
            openrouter_key = get_paid_key() or (get_free_keys()[0] if get_free_keys() else None)

        groq_key = (
            self.settings.get("api_keys", {}).get("groq")
            or os.getenv("GROQ_API_KEY")
        )
        if not groq_key:
            from monika.infrastructure.api.groq_rate_limiter import get_api_keys
            g_keys = get_api_keys()
            if g_keys:
                groq_key = g_keys[0]

        gemini_key = (
            self.settings.get("api_keys", {}).get("gemini")
            or os.getenv("GEMINI_API_KEY")
        )
        if not gemini_key:
            keys = os.getenv("GEMINI_API_KEYS", "")
            if keys:
                gemini_key = keys.split(",")[0].strip()

        try:
            import aiohttp
            async with aiohttp.ClientSession() as http_session:
                for model_name in candidate_models:
                    m_lower = model_name.lower()

                    # A. OpenRouter Whisper endpoint
                    if ("whisper" in m_lower and ("openai/" in m_lower or "/" in m_lower)) or "openrouter" in m_lower:
                        if not openrouter_key:
                            continue
                        clean_model = model_name
                        if clean_model.startswith("openrouter/"):
                            clean_model = clean_model[len("openrouter/"):]
                        try:
                            form = aiohttp.FormData()
                            form.add_field("file", audio, filename="audio.ogg", content_type=mime_type)
                            form.add_field("model", clean_model)
                            headers = {"Authorization": f"Bearer {openrouter_key}"}
                            url = "https://openrouter.ai/api/v1/audio/transcriptions"
                            async with http_session.post(url, data=form, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    text = data.get("text", "")
                                    if text and str(text).strip():
                                        return str(text).strip()
                                else:
                                    err_body = await resp.text()
                                    logger.warning(f"[VoiceHandler] OpenRouter transcription ({clean_model}) status {resp.status}: {err_body}")
                        except Exception as e:
                            logger.warning(f"[VoiceHandler] OpenRouter transcription failed for {clean_model}: {e}")

                    # B. Groq Whisper endpoint
                    elif "whisper" in m_lower and "/" not in m_lower:
                        if not groq_key:
                            continue
                        try:
                            form = aiohttp.FormData()
                            form.add_field("file", audio, filename="audio.ogg", content_type=mime_type)
                            form.add_field("model", model_name)
                            headers = {"Authorization": f"Bearer {groq_key}"}
                            url = "https://api.groq.com/openai/v1/audio/transcriptions"
                            async with http_session.post(url, data=form, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    text = data.get("text", "")
                                    if text and str(text).strip():
                                        return str(text).strip()
                                else:
                                    err_body = await resp.text()
                                    logger.warning(f"[VoiceHandler] Groq transcription ({model_name}) status {resp.status}: {err_body}")
                        except Exception as e:
                            logger.warning(f"[VoiceHandler] Groq transcription failed for {model_name}: {e}")

                    # C. Gemini multimodal endpoint
                    elif "gemini" in m_lower or not ("whisper" in m_lower):
                        if not gemini_key:
                            continue
                        clean_gemini_model = model_name
                        if clean_gemini_model.startswith("google/"):
                            clean_gemini_model = clean_gemini_model[len("google/"):]
                        b64_audio = base64.b64encode(audio).decode("utf-8") if isinstance(audio, (bytes, bytearray)) else audio
                        headers = {
                            "x-goog-api-key": gemini_key,
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
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_gemini_model}:generateContent"
                        try:
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
                                    logger.warning(f"[VoiceHandler] Direct Gemini transcription ({clean_gemini_model}) status {resp.status}: {err_body}")
                        except Exception as e:
                            logger.warning(f"[VoiceHandler] Direct Gemini transcription failed for {clean_gemini_model}: {e}")
        except Exception as e:
            logger.warning(f"[VoiceHandler] Transcription execution failed: {e}")

        return ""
