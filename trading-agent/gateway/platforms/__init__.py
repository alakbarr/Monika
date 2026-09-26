# ==============================================================================
# File: gateway/platforms/__init__.py
# ==============================================================================

from gateway.platforms.webhook_adapter import WebhookPlatformAdapter
from gateway.platforms.discord_adapter import DiscordPlatformAdapter
from gateway.platforms.slack_adapter import SlackPlatformAdapter
from gateway.platforms.telegram_adapter import TelegramPlatformAdapter

__all__ = [
    "WebhookPlatformAdapter",
    "DiscordPlatformAdapter",
    "SlackPlatformAdapter",
    "TelegramPlatformAdapter",
]
