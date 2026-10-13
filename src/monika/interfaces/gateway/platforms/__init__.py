# ==============================================================================
# File: gateway/platforms/__init__.py
# ==============================================================================

from monika.interfaces.gateway.platforms.discord_adapter import DiscordPlatformAdapter
from monika.interfaces.gateway.platforms.slack_adapter import SlackPlatformAdapter
from monika.interfaces.gateway.platforms.telegram_adapter import TelegramPlatformAdapter
from monika.interfaces.gateway.platforms.webhook_adapter import WebhookPlatformAdapter

__all__ = [
    "WebhookPlatformAdapter",
    "DiscordPlatformAdapter",
    "SlackPlatformAdapter",
    "TelegramPlatformAdapter",
]
