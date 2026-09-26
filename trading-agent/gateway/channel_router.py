# ==============================================================================
# File: gateway/channel_router.py
# ==============================================================================

"""
Unified Channel Router & Session Multiplexer.
Institutional-grade engine turn protection architecture.

Routes incoming messages from any messaging platform (Telegram, Discord, Slack, Webhook)
into durable sessions backed by SessionDbWal, ensuring consistent memory and state across channels.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from database.session_db_wal import SessionDbWal
from gateway.platform_base import BasePlatformAdapter

logger = logging.getLogger("TradingAgent.Gateway.ChannelRouter")


class ChannelRouter:
    """Multi-platform session dispatcher."""

    def __init__(self, db: SessionDbWal):
        self.db = db
        self.adapters: Dict[str, BasePlatformAdapter] = {}
        self.session_map: Dict[str, str] = {}  # "platform:channel" -> session_id
        self.message_pipeline: Optional[Callable[[str, str, Dict[str, Any]], asyncio.Future]] = None

    def register_adapter(self, adapter: BasePlatformAdapter) -> None:
        """Register a platform adapter with this router."""
        self.adapters[adapter.platform_name] = adapter
        adapter.register_handler(self.handle_incoming_message)
        logger.info(f"[ChannelRouter] Registered platform adapter '{adapter.platform_name}'.")

    def set_pipeline(
        self,
        pipeline_fn: Callable[[str, str, Dict[str, Any]], asyncio.Future],
    ) -> None:
        """Set the agent execution callback (session_id, user_text, metadata) -> reply_text."""
        self.message_pipeline = pipeline_fn

    def resolve_session_id(self, platform: str, channel_id: str) -> str:
        """Resolve or create a deterministic session ID for a channel."""
        key = f"{platform}:{channel_id}"
        if key not in self.session_map:
            self.session_map[key] = f"sess_{platform}_{channel_id}"
        return self.session_map[key]

    async def handle_incoming_message(
        self,
        sender_id: str,
        channel_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> str:
        """Handle incoming message from any registered platform."""
        platform = metadata.get("platform", "generic")
        session_id = self.resolve_session_id(platform, channel_id)

        # 1. Log to SessionDbWal
        turn_ordinal = int(metadata.get("turn_ordinal", 1))
        self.db.append_message(
            session_id=session_id,
            role="user",
            content=text,
            turn_ordinal=turn_ordinal,
        )

        reply_text = ""
        # 2. Invoke pipeline if registered
        if self.message_pipeline:
            try:
                reply_text = await self.message_pipeline(session_id, text, metadata)
            except Exception as e:
                logger.error(f"[ChannelRouter] Error in agent pipeline: {e}", exc_info=True)
                reply_text = f"Error processing request: {e}"
        else:
            reply_text = f"[Echo from Monika Gateway]: Received '{text}'"

        # 3. Log assistant reply to SessionDbWal
        self.db.append_message(
            session_id=session_id,
            role="assistant",
            content=reply_text,
            turn_ordinal=turn_ordinal,
        )

        # 4. Dispatch reply back to platform
        adapter = self.adapters.get(platform)
        if adapter and adapter.is_connected:
            await adapter.send_message(channel_id, reply_text, metadata)

        return reply_text
