# ==============================================================================
# File: telegram_bot/chat_agent.py
# Monika Telegram Presentation Adapter & Streaming Interface
# ==============================================================================

"""
Telegram Chat Agent Adapter — Presentation & Streaming Interface via Telegram.

Subclasses CoreChatAgent from agent.chat_agent and handles:
1. Telegram Update unpacking and inline keyboard confirmation cards.
2. Real-time response streaming via OmnichannelStreamer to Telegram message bubbles.
3. Telegram-specific error handling and text length chunking (TELEGRAM_MAX_CHARS = 4096).
4. Full backward-compatible exports and transparent test patch synchronization.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from typing import Any, Optional, Union

try:
    from telegram.error import RetryAfter, BadRequest
except ImportError:
    class _FallbackRetryAfter(Exception):
        retry_after = 1.0
    class _FallbackBadRequest(Exception):
        pass
    RetryAfter = _FallbackRetryAfter
    BadRequest = _FallbackBadRequest

from monika.application.agent.chat_agent import (
    ChatAgent as CoreChatAgent,
    PendingAction,
    HISTORY_WINDOW,
    MAX_HISTORY_CHARS,
    SESSION_TIMEOUT_HOURS,
    _sanitize_chat_format,
    get_client_for_task,
    get_session,
)
from monika.application.agent import chat_agent as _core_agent

logger = logging.getLogger("TradingAgent.TelegramChatAgent")

TELEGRAM_MAX_CHARS = 4096
_sanitize_telegram_format = _sanitize_chat_format


class _TelegramChatAgentMeta(type):
    """Metaclass to transparently synchronize class-level patches (e.g. ChatAgent.handle) to CoreChatAgent."""
    _orig_attrs: dict[str, Any] = {}

    def __setattr__(cls, name: str, value: Any) -> None:
        if name not in cls._orig_attrs and hasattr(CoreChatAgent, name):
            cls._orig_attrs[name] = getattr(CoreChatAgent, name)
        super().__setattr__(name, value)
        if hasattr(CoreChatAgent, name) and name not in ("__module__", "__doc__"):
            if name in cls._orig_attrs and value is cls._orig_attrs[name]:
                setattr(CoreChatAgent, name, cls._orig_attrs.pop(name))
            else:
                setattr(CoreChatAgent, name, value)

    def __delattr__(cls, name: str) -> None:
        super().__delattr__(name)
        if name in cls._orig_attrs:
            orig = cls._orig_attrs.pop(name)
            setattr(CoreChatAgent, name, orig)


class TelegramChatAgent(CoreChatAgent, metaclass=_TelegramChatAgentMeta):
    """
    Telegram-specialized ChatAgent presentation adapter.
    Enriches CoreChatAgent with Telegram-specific message streaming,
    live bubble updates, and interactive inline confirmation cards.
    """

    async def _handle_streaming(
        self,
        update: Any,
        context: Any,
        user_message: str,
        session_id: Optional[str] = None,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Handle chat turn with real-time token streaming via edit_message_text."""
        async with get_session() as session:
            history = await self._load_history(session, session_id=session_id)
            await self._save_message(session, "user", user_message, session_id=session_id)
            system_prompt = await self._build_system_prompt(session)

            preference = self._detect_model_preference(user_message)
            clean_message = user_message
            if preference == 'deep_research':
                clean_message = re.sub(r'^/research\s*', '', user_message, flags=re.IGNORECASE)
            elif preference in ('tier_lite', 'gemini_lite'):
                preference = 'tier_lite'
                clean_message = re.sub(r'^/(fast|quick)\s+', '', user_message, flags=re.IGNORECASE)
            elif preference in ('tier_medium', 'groq_medium'):
                preference = 'tier_medium'
                clean_message = re.sub(r'^/(medium|mid)\s+', '', user_message, flags=re.IGNORECASE)
            elif preference in ('tier_deep', 'claude_sonnet'):
                preference = 'tier_deep'
                clean_message = re.sub(r'^/(analyze|analisis)\s+', '', user_message, flags=re.IGNORECASE)

            if preference == 'auto':
                complexity = await self._classify_query_complexity(clean_message)
                if complexity == 'deep_research':
                    preference = 'deep_research'
                elif complexity == 'complex':
                    preference = 'tier_deep'
                else:
                    preference = 'tier_lite'

            selected_tools = self._tool_router.route_tools_for_query(clean_message)
            needs_tools = bool(selected_tools) or bool(
                re.search(
                    r'\b(posisi|order|orders|harga|price|chart|saldo|equity|balance|pnl|profit|loss|close|buy|sell|debat|analisis|analisa|setup|market|vix|dxy|cot|fedwatch|alpha|factor|factors)\b',
                    clean_message,
                    re.IGNORECASE,
                )
            )

            if preference == 'deep_research' or needs_tools:
                reply, pending = await self._handle_internal(
                    user_message=clean_message,
                    session_id=session_id,
                    typing_callback=typing_callback,
                    status_callback=status_callback,
                )

                async def _text_chunk_gen():
                    chunk_size = 30
                    for i in range(0, len(reply), chunk_size):
                        yield reply[i:i + chunk_size]
                        await asyncio.sleep(0.01)

                streamed_res = await self._stream_response(update, context, _text_chunk_gen())
                self._last_turn_streamed = True
                self.was_last_turn_streamed = True
                return (streamed_res or reply), pending

            system_prompt = self._inject_macro_playbooks(system_prompt, user_query=clean_message)

            if preference in ("tier_deep", "claude_sonnet"):
                generator = await self._run_with_claude(
                    system_prompt, history, clean_message, stream=True
                )
            else:
                generator = await self._run_with_gemini(
                    system_prompt, history, clean_message, stream=True
                )

            final_text = await self._stream_response(update, context, generator)
            await self._save_message(session, "assistant", final_text, session_id=session_id)
            self._last_turn_streamed = True
            self.was_last_turn_streamed = True
            return final_text, None


    async def _stream_response(
        self,
        update: Any,
        context: Any,
        response_generator: Any,
    ) -> str:
        """Stream LLM tokens via OmnichannelStreamer with adaptive throttle, 3-strikes 429 flood control, and splitting."""
        from monika.interfaces.gateway.omnichannel_streamer import OmnichannelStreamer
        from monika.interfaces.telegram.sanitizer import sanitize_telegram_html

        initial_msg: Optional[Any] = None
        if hasattr(update, "message") and update.message:
            try:
                initial_msg = await update.message.reply_text("[PROSES] Thinking...")
            except Exception:
                pass
        elif hasattr(update, "reply_text"):
            try:
                initial_msg = await update.reply_text("[PROSES] Thinking...")
            except Exception:
                pass

        async def _send_next_bubble(txt: str) -> Any:
            display = sanitize_telegram_html(txt)
            if hasattr(update, "message") and update.message:
                return await update.message.reply_text(display, parse_mode="HTML")
            elif hasattr(update, "reply_text"):
                return await update.reply_text(display, parse_mode="HTML")
            return None

        async def _edit_bubble(msg: Any, txt: str) -> None:
            display = sanitize_telegram_html(txt)
            if len(display) <= 4096:
                await msg.edit_text(display, parse_mode="HTML")

        streamer = OmnichannelStreamer(
            send_message_fn=_send_next_bubble,
            edit_message_fn=_edit_bubble,
            initial_interval=1.2,
            max_interval=4.0,
            max_chars_per_message=3850,
        )
        if initial_msg is not None:
            streamer._active_message = initial_msg

        async for delta in response_generator:
            text_chunk = delta if isinstance(delta, str) else getattr(delta, "text", str(delta))
            await streamer.feed_token(text_chunk)

        final_buffer = await streamer.finish()
        return final_buffer


# Backward-compatible alias
ChatAgent = TelegramChatAgent

__all__ = [
    "ChatAgent",
    "TelegramChatAgent",
    "PendingAction",
    "TELEGRAM_MAX_CHARS",
    "HISTORY_WINDOW",
    "MAX_HISTORY_CHARS",
    "SESSION_TIMEOUT_HOURS",
    "_sanitize_telegram_format",
    "get_client_for_task",
    "get_session",
]

# Module proxy to mirror unittest.mock patches on telegram_bot.chat_agent
# directly to agent.chat_agent for seamless backward compatibility.
class _TelegramChatAgentModule(sys.modules[__name__].__class__):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in ("get_client_for_task", "get_session"):
            setattr(_core_agent, name, value)
        elif name == "ChatAgent":
            if value is TelegramChatAgent:
                setattr(_core_agent, "ChatAgent", CoreChatAgent)
            else:
                setattr(_core_agent, "ChatAgent", value)

sys.modules[__name__].__class__ = _TelegramChatAgentModule
