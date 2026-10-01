# ==============================================================================
# File: gateway/platforms/slack_adapter.py
# ==============================================================================

"""
Slack Platform Adapter for Omnichannel Gateway.
Institutional-grade engine turn protection architecture.

Enables communication with Slack workspaces via Incoming Webhooks or Web API,
supporting outbound messages, Slack blocks formatting, and inbound Events API.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Dict, List, Optional
import httpx

from gateway.platform_base import BasePlatformAdapter

logger = logging.getLogger("TradingAgent.Gateway.SlackAdapter")


class SlackPlatformAdapter(BasePlatformAdapter):
    """Adapter for Slack messaging channels."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        super().__init__(platform_name="slack")
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.sent_messages: List[Dict[str, Any]] = []
        self._http_client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialize HTTP client for Slack communication."""
        self._http_client = httpx.AsyncClient(timeout=15.0)
        self.is_connected = True
        logger.info("[SlackAdapter] Connected to Slack adapter.")

    async def stop(self) -> None:
        """Close HTTP client and clean up connections."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self.is_connected = False
        logger.info("[SlackAdapter] Disconnected Slack adapter.")

    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send outgoing message to a Slack channel or webhook.
        If webhook_url is configured, delivers payload via Slack Incoming Webhook.
        If bot_token is configured, delivers via Slack Web API (chat.postMessage).
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
                payload: Dict[str, Any] = {"text": content}
                if metadata and "blocks" in metadata:
                    payload["blocks"] = metadata["blocks"]
                resp = await client.post(webhook_target, json=payload)
                if resp.status_code == 200 and resp.text.strip().lower() == "ok":
                    logger.debug(f"[SlackAdapter] Delivered webhook message to Slack {target_id}")
                    delivered = True
                else:
                    logger.warning(
                        f"[SlackAdapter] Webhook delivery failed with HTTP {resp.status_code}: {resp.text[:120]}"
                    )
            elif self.bot_token and target_id and not target_id.startswith("slack_ch_") and not target_id.startswith("sim_"):
                api_url = "https://slack.com/api/chat.postMessage"
                headers = {
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                }
                payload = {
                    "channel": target_id,
                    "text": content,
                }
                if metadata and "blocks" in metadata:
                    payload["blocks"] = metadata["blocks"]
                resp = await client.post(api_url, headers=headers, json=payload)
                data = resp.json() if resp.status_code == 200 else {}
                if data.get("ok"):
                    logger.debug(f"[SlackAdapter] Delivered chat.postMessage to Slack #{target_id}")
                    delivered = True
                else:
                    logger.warning(
                        f"[SlackAdapter] Bot delivery failed: {data.get('error', resp.text[:120])}"
                    )
            else:
                # Dry-run or test channel
                delivered = True
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to dispatch Slack message: {e}")
            delivered = False
        finally:
            if close_client:
                await client.aclose()

        return delivered

    async def handle_inbound_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle inbound Slack Events API payload.
        - url_verification: returns challenge for endpoint verification.
        - event_callback: forwards message / app_mention to message_handler.
        """
        event_type = payload.get("type")
        if event_type == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        if event_type == "event_callback":
            event = payload.get("event", {})
            user_id = str(event.get("user", "slack_user"))
            channel_id = str(event.get("channel", "general"))
            text = str(event.get("text", ""))

            # Avoid bot echo loops
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return {"status": "ignored_bot_event"}

            reply = ""
            if self.message_handler and text:
                meta = {
                    "platform": "slack",
                    "user_id": user_id,
                    "event_id": payload.get("event_id"),
                    "thread_ts": event.get("thread_ts"),
                }
                reply = await self.message_handler(user_id, channel_id, text, meta)
            return {"status": "ok", "reply_length": len(reply)}

        return {"status": "unhandled_event"}

    async def simulate_incoming(self, user_id: str, channel_id: str, message: str) -> str:
        """Simulate or inject incoming message from Slack."""
        meta = {"platform": "slack", "user_id": user_id}
        if self.message_handler:
            return await self.message_handler(user_id, channel_id, message, meta)
        return ""
