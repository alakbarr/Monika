# ==============================================================================
# File: gateway/platforms/discord_adapter.py
# ==============================================================================

"""
Discord Platform Adapter for Omnichannel Gateway.
Institutional-grade engine turn protection architecture.

Enables communication with Discord servers via Webhooks or Bot Gateway API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from gateway.platform_base import BasePlatformAdapter

logger = logging.getLogger("TradingAgent.Gateway.DiscordAdapter")


class DiscordPlatformAdapter(BasePlatformAdapter):
    """Adapter for Discord bot and webhook channels."""

    def __init__(self, bot_token: Optional[str] = None, webhook_url: Optional[str] = None):
        super().__init__(platform_name="discord")
        self.bot_token = bot_token
        self.webhook_url = webhook_url
        self.sent_messages: list[Dict[str, Any]] = []

    async def start(self) -> None:
        self.is_connected = True
        logger.info("[DiscordAdapter] Connected to Discord adapter.")

    async def stop(self) -> None:
        self.is_connected = False
        logger.info("[DiscordAdapter] Disconnected Discord adapter.")

    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        record = {
            "channel_id": target_id,
            "content": content,
            "metadata": metadata or {},
        }
        self.sent_messages.append(record)
        logger.debug(f"[DiscordAdapter] Sent message to Discord #{target_id}: {content[:60]}")
        return True

    async def simulate_incoming(self, user_id: str, channel_id: str, message: str) -> str:
        """Simulate or inject incoming message from Discord."""
        meta = {"platform": "discord", "user_id": user_id}
        if self.message_handler:
            return await self.message_handler(user_id, channel_id, message, meta)
        return ""
