# ==============================================================================
# File: gateway/platforms/telegram_adapter.py
# ==============================================================================

"""
Telegram Platform Adapter for Omnichannel Gateway.
Institutional-grade engine turn protection architecture.

Integrates Telegram Bot interactions into the unified ChannelRouter architecture.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from monika.interfaces.gateway.bot_loop_guard import BotLoopGuard
from monika.interfaces.gateway.platform_base import BasePlatformAdapter
from monika.interfaces.gateway.turn_lease import TurnLeaseManager

logger = logging.getLogger("TradingAgent.Gateway.TelegramAdapter")


class TelegramPlatformAdapter(BasePlatformAdapter):
    """
    Adapter bridging Telegram messaging into the unified ChannelRouter.
    Features:
    - BotLoopGuard protection against automated echo loops
    - TurnLeaseManager protection against concurrency races
    - Inbound debouncing & batching for burst messages
    - Clean emoji sanitization & dispatch recording
    - Backward-compatible facade integration with telegram_bot.bot.TelegramBot
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        turn_lease_manager: Optional[TurnLeaseManager] = None,
        bot_loop_guard: Optional[BotLoopGuard] = None,
        debounce_window_s: float = 0.35,
    ):
        super().__init__(platform_name="telegram")
        self.bot_token = bot_token
        self.sent_messages: List[Dict[str, Any]] = []
        self.turn_lease_mgr = turn_lease_manager or TurnLeaseManager()
        self.loop_guard = bot_loop_guard or BotLoopGuard()
        self.debounce_window_s = debounce_window_s
        self._debounce_buffers: Dict[str, List[str]] = {}
        self._debounce_tasks: Dict[str, asyncio.Task] = {}
        self._debounce_futures: Dict[str, List[asyncio.Future[str]]] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._bot_instance: Optional[Any] = None

    def attach_bot_instance(self, bot: Any) -> None:
        """Attach active TelegramBot runtime instance."""
        self._bot_instance = bot

    async def start(self) -> None:
        self.is_connected = True
        logger.info("[TelegramAdapter] Telegram gateway adapter started.")

    async def stop(self) -> None:
        self.is_connected = False
        for task in self._debounce_tasks.values():
            if not task.done():
                task.cancel()
        self._debounce_tasks.clear()
        self._debounce_buffers.clear()
        for fut_list in self._debounce_futures.values():
            for f in fut_list:
                if not f.done():
                    f.cancel()
        self._debounce_futures.clear()
        logger.info("[TelegramAdapter] Telegram gateway adapter stopped.")

    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            from monika.interfaces.telegram.sanitizer import strip_emojis_and_emoticons

            content = strip_emojis_and_emoticons(content)
        except Exception:
            pass

        record = {
            "chat_id": target_id,
            "content": content,
            "metadata": metadata or {},
        }
        self.sent_messages.append(record)

        if self._bot_instance and hasattr(self._bot_instance, "send_notification"):
            try:
                chat_id_int = int(target_id) if target_id.lstrip("-").isdigit() else None
                if chat_id_int:
                    task = asyncio.create_task(self._bot_instance.send_notification(content, chat_id=chat_id_int))
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
            except Exception as e:
                logger.debug(f"[TelegramAdapter] Real bot dispatch deferred: {e}")

        logger.debug(f"[TelegramAdapter] Dispatched message to Telegram chat {target_id}: {content[:60]}")
        return True

    async def handle_debounced_incoming(
        self,
        chat_id: str,
        user_id: str,
        message: str,
    ) -> str:
        """
        Ingest incoming message with debouncing & batching.
        Buffers bursts within debounce_window_s and processes as a single combined message.
        """
        key = f"{chat_id}:{user_id}"
        if key not in self._debounce_buffers:
            self._debounce_buffers[key] = []
        self._debounce_buffers[key].append(message.strip())

        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        if key not in self._debounce_futures:
            self._debounce_futures[key] = []
        self._debounce_futures[key].append(future)

        if key in self._debounce_tasks and not self._debounce_tasks[key].done():
            self._debounce_tasks[key].cancel()

        async def _flush_after_delay():
            try:
                await asyncio.sleep(self.debounce_window_s)
            except asyncio.CancelledError:
                return

            buffered_msgs = self._debounce_buffers.pop(key, [])
            pending_futures = self._debounce_futures.pop(key, [])
            combined_text = "\n".join(buffered_msgs)
            try:
                res = await self.simulate_incoming(chat_id, user_id, combined_text)
                for f in pending_futures:
                    if not f.done():
                        f.set_result(res)
            except Exception as e:
                for f in pending_futures:
                    if not f.done():
                        f.set_exception(e)

        flush_task = asyncio.create_task(_flush_after_delay())
        self._debounce_tasks[key] = flush_task
        self._background_tasks.add(flush_task)
        flush_task.add_done_callback(self._background_tasks.discard)
        return await future

    async def simulate_incoming(self, chat_id: str, user_id: str, message: str) -> str:
        """Process incoming telegram message through loop guard, turn lease, and router."""
        is_allowed, reason = self.loop_guard.check_and_record(
            platform="telegram",
            chat_id=chat_id,
            sender_id=user_id,
            text=message,
        )
        if not is_allowed:
            logger.warning(f"[TelegramAdapter] Bot loop detected and blocked: {reason}")
            return f"[BLOCKED] Automated loop detected: {reason}"

        conversation_id = f"tg_{chat_id}"
        holder_id = f"user_{user_id}_{int(time.time() * 1000)}"
        acquired = await self.turn_lease_mgr.acquire_lease(conversation_id, holder_id)
        if not acquired:
            logger.warning(f"[TelegramAdapter] Concurrency race rejected for {conversation_id}")
            return "[BUSY] Sesi chat sedang memproses giliran sebelumnya. Mohon tunggu sebentar."

        try:
            meta = {"platform": "telegram", "user_id": user_id}
            if self.message_handler:
                return await self.message_handler(user_id, chat_id, message, meta)
            return ""
        finally:
            await self.turn_lease_mgr.release_lease(conversation_id, holder_id)
