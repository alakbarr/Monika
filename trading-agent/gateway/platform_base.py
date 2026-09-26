# ==============================================================================
# File: gateway/platform_base.py
# ==============================================================================

"""
Base Platform Adapter Interface for Omnichannel Messaging Gateway.
Institutional-grade engine turn protection architecture.

Defines the contract for real-time bi-directional messaging across multiple platforms
(Telegram, Discord, Slack, WhatsApp, Signal, Webhook).
"""

from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("TradingAgent.Gateway.PlatformBase")


class BasePlatformAdapter(abc.ABC):
    """Abstract interface for messaging platforms."""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.is_connected: bool = False
        self.message_handler: Optional[Callable[[str, str, str, Dict[str, Any]], asyncio.Future]] = None

    def register_handler(
        self,
        handler: Callable[[str, str, str, Dict[str, Any]], asyncio.Future],
    ) -> None:
        """Register the message intake callback (sender_id, channel_id, text, metadata)."""
        self.message_handler = handler

    @abc.abstractmethod
    async def start(self) -> None:
        """Connect to the platform API/websocket/polling loop."""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Disconnect and clean up platform connections."""
        pass

    @abc.abstractmethod
    async def send_message(
        self,
        target_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send outgoing message to a channel or user."""
        pass
