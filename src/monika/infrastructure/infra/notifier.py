"""
Backward-compatibility facade for AgentNotifier.
Canonical location: monika.infrastructure.notifications.telegram_notifier
"""

import sys
import monika.infrastructure.notifications.telegram_notifier as _canonical

from monika.infrastructure.notifications.telegram_notifier import (
    AgentNotifier,
    Bot,
    get_notifier,
    sanitize_telegram_html,
)

__all__ = ["AgentNotifier", "get_notifier", "Bot", "sanitize_telegram_html"]

sys.modules[__name__] = _canonical
