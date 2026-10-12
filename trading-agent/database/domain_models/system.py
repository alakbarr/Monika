# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.system
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.system"""

import sys
import monika.infrastructure.database.domain_models.system as _canonical

from monika.infrastructure.database.domain_models.system import (
    ActivityLog,
    RiskState,
    SystemConfig,
    TelegramConversation,
    TelegramTopicBinding,
    TokenUsageLog,
    TradingEvent,
    UserJournalEntry,
    UserPreference,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ActivityLog",
    "RiskState",
    "SystemConfig",
    "TelegramConversation",
    "TelegramTopicBinding",
    "TokenUsageLog",
    "TradingEvent",
    "UserJournalEntry",
    "UserPreference",
]
