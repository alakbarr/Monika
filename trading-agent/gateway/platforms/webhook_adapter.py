# ==============================================================================
# File: gateway/platforms/webhook_adapter.py
# ==============================================================================

"""
REST Webhook Adapter for Omnichannel Gateway.
Institutional-grade engine turn protection architecture.

Enables third-party systems, trading alerts (TradingView webhooks),
and custom applications to communicate with Monika via HTTP JSON requests.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from gateway.platform_base import BasePlatformAdapter

logger = logging.getLogger("TradingAgent.Gateway.WebhookAdapter")


class WebhookPlatformAdapter(BasePlatformAdapter):
    """Adapter for HTTP Webhook integrations."""

    def __init__(self, platform_name: str = "webhook"):
        super().__init__(platform_name=platform_name)
        self.sent_messages: list[Dict[str, Any]] = []

    async def start(self) -> None:
        self.is_connected = True
        logger.info("[WebhookAdapter] Ready to receive webhook events.")

    async def stop(self) -> None:
        self.is_connected = False
        logger.info("[WebhookAdapter] Webhook adapter stopped.")

    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        # In a webhook setup, response is either returned synchronously or posted to target webhook URL
        record = {
            "target_id": target_id,
            "content": content,
            "metadata": metadata or {},
        }
        self.sent_messages.append(record)
        logger.debug(f"[WebhookAdapter] Dispatched message to {target_id}: {content[:60]}")
        return True

    async def inject_incoming_webhook(
        self,
        sender_id: str,
        channel_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Entry point called by HTTP server upon receiving an inbound webhook POST."""
        meta = metadata or {}
        meta["platform"] = self.platform_name
        if self.message_handler:
            return await self.message_handler(sender_id, channel_id, text, meta)
        return "Webhook received but no handler registered."
