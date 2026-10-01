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
from typing import Any, Callable, Dict, Optional

from gateway.platform_base import BasePlatformAdapter

logger = logging.getLogger("TradingAgent.Gateway.TelegramAdapter")


class TelegramPlatformAdapter(BasePlatformAdapter):
    """Adapter bridging Telegram messaging into the gateway."""

    def __init__(self, bot_token: Optional[str] = None):
        super().__init__(platform_name="telegram")
        self.bot_token = bot_token
        self.sent_messages: list[Dict[str, Any]] = []

    async def start(self) -> None:
        self.is_connected = True
        logger.info("[TelegramAdapter] Telegram gateway adapter started.")

    async def stop(self) -> None:
        self.is_connected = False
        logger.info("[TelegramAdapter] Telegram gateway adapter stopped.")

    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            from telegram_bot.sanitizer import strip_emojis_and_emoticons
            content = strip_emojis_and_emoticons(content)
        except Exception:
            pass

        record = {
            "chat_id": target_id,
            "content": content,
            "metadata": metadata or {},
        }
        self.sent_messages.append(record)
        logger.debug(f"[TelegramAdapter] Dispatched message to Telegram chat {target_id}: {content[:60]}")
        return True

    async def simulate_incoming(self, chat_id: str, user_id: str, message: str) -> str:
        """Process incoming telegram message through the router."""
        meta = {"platform": "telegram", "user_id": user_id}
        if self.message_handler:
            return await self.message_handler(user_id, chat_id, message, meta)
        return ""
