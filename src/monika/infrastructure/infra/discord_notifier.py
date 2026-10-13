"""
Backward-compatibility facade for DiscordNotifier.
Canonical location: monika.infrastructure.notifications.discord_notifier
"""

import sys
import monika.infrastructure.notifications.discord_notifier as _canonical

from monika.infrastructure.notifications.discord_notifier import DiscordNotifier

__all__ = ["DiscordNotifier"]

sys.modules[__name__] = _canonical
