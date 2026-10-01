# ==============================================================================
# File: gateway/platforms/discord_adapter.py
# ==============================================================================

"""
Discord Platform Adapter for Omnichannel Gateway.
Institutional-grade engine turn protection architecture.

Enables bi-directional communication with Discord servers via Webhooks or Bot REST API,
supporting outbound alerts/chat, embed cards, and inbound message handling.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Dict, List, Optional
import httpx

from gateway.platform_base import BasePlatformAdapter

logger = logging.getLogger("TradingAgent.Gateway.DiscordAdapter")


class DiscordPlatformAdapter(BasePlatformAdapter):
    """Adapter for Discord bot and webhook channels."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        super().__init__(platform_name="discord")
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.sent_messages: List[Dict[str, Any]] = []
        self._http_client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialize HTTP client for Discord communication."""
        self._http_client = httpx.AsyncClient(timeout=15.0)
        self.is_connected = True
        logger.info("[DiscordAdapter] Connected to Discord adapter.")

    async def stop(self) -> None:
        """Close HTTP client and clean up connections."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self.is_connected = False
        logger.info("[DiscordAdapter] Disconnected Discord adapter.")

    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send outgoing message to a Discord channel or webhook.
        If webhook_url is configured, delivers payload via Discord webhook.
        If bot_token is configured, delivers via Discord REST API to channel.
        Always records in self.sent_messages for audit, telemetry, and testing.
        """
        try:
            from telegram_bot.sanitizer import strip_emojis_and_emoticons
            content = strip_emojis_and_emoticons(content)
        except Exception:
            pass

        record = {
            "channel_id": target_id,
            "content": content,
            "metadata": metadata or {},
        }
        self.sent_messages.append(record)

        client = self._http_client or httpx.AsyncClient(timeout=15.0)
        close_client = self._http_client is None

        delivered = False
        try:
            webhook_target = (metadata or {}).get("webhook_url") or self.webhook_url
            if webhook_target:
                payload: Dict[str, Any] = {"content": content}
                if metadata and "embeds" in metadata:
                    payload["embeds"] = metadata["embeds"]
                resp = await client.post(webhook_target, json=payload)
                if resp.status_code in (200, 204):
                    logger.debug(f"[DiscordAdapter] Delivered webhook message to Discord #{target_id}")
                    delivered = True
                else:
                    logger.warning(
                        f"[DiscordAdapter] Webhook delivery failed with HTTP {resp.status_code}: {resp.text[:120]}"
                    )
            elif self.bot_token and target_id and not target_id.startswith("disc_ch_"):
                api_url = f"https://discord.com/api/v10/channels/{target_id}/messages"
                headers = {
                    "Authorization": f"Bot {self.bot_token}",
                    "Content-Type": "application/json",
                }
                payload = {"content": content}
                if metadata and "embeds" in metadata:
                    payload["embeds"] = metadata["embeds"]
                resp = await client.post(api_url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    logger.debug(f"[DiscordAdapter] Delivered bot message to Discord #{target_id}")
                    delivered = True
                else:
                    logger.warning(
                        f"[DiscordAdapter] Bot delivery failed with HTTP {resp.status_code}: {resp.text[:120]}"
                    )
            else:
                # Dry-run or test channel
                delivered = True
        except Exception as e:
            logger.error(f"[DiscordAdapter] Failed to dispatch Discord message: {e}")
            delivered = False
        finally:
            if close_client:
                await client.aclose()

        return delivered

    async def handle_inbound_interaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle inbound webhook/interaction payload from Discord.
        Type 1: PING (returns PONG for endpoint verification)
        Type 2/4: Application Command / Message
        """
        interaction_type = payload.get("type", 0)
        if interaction_type == 1:
            return {"type": 1}

        user_id = str(
            payload.get("member", {}).get("user", {}).get("id")
            or payload.get("user", {}).get("id", "discord_user")
        )
        channel_id = str(payload.get("channel_id", "default_channel"))
        data = payload.get("data", {})
        message_text = (
            data.get("options", [{}])[0].get("value", "")
            if data.get("options")
            else data.get("name", "")
        )

        reply = ""
        if self.message_handler and message_text:
            meta = {
                "platform": "discord",
                "user_id": user_id,
                "interaction_id": payload.get("id"),
            }
            reply = await self.message_handler(user_id, channel_id, message_text, meta)

        return {
            "type": 4,
            "data": {
                "content": reply or "Received request, processing with Monika agent.",
            },
        }

    async def simulate_incoming(self, user_id: str, channel_id: str, message: str) -> str:
        """Simulate or inject incoming message from Discord."""
        meta = {"platform": "discord", "user_id": user_id}
        if self.message_handler:
            return await self.message_handler(user_id, channel_id, message, meta)
        return ""
