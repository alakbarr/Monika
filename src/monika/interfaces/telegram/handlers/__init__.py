# ==============================================================================
# File: interfaces/telegram/handlers/__init__.py
# ==============================================================================

"""
Telegram Bot Handlers Package.
Provides modular command descriptors, categories, and routing maps.
"""

from monika.interfaces.telegram.handlers.admin_commands import TelegramAdminCommandsMixin
from monika.interfaces.telegram.handlers.callback_handler import TelegramCallbackHandlerMixin
from monika.interfaces.telegram.handlers.market_commands import (
    MARKET_COMMAND_DESCRIPTORS,
    MarketCommandDescriptor,
    TelegramMarketCommandsMixin,
)
from monika.interfaces.telegram.handlers.media_handlers import TelegramMediaHandlerMixin
from monika.interfaces.telegram.handlers.system_commands import (
    SYSTEM_COMMAND_DESCRIPTORS,
    SystemCommandDescriptor,
    TelegramSystemCommandsMixin,
)
from monika.interfaces.telegram.handlers.trading_commands import (
    TRADING_COMMAND_DESCRIPTORS,
    CommandDescriptor,
    TelegramTradingCommandsMixin,
    execute_trading_command,
)

__all__ = [
    "CommandDescriptor",
    "TRADING_COMMAND_DESCRIPTORS",
    "execute_trading_command",
    "TelegramTradingCommandsMixin",
    "MarketCommandDescriptor",
    "MARKET_COMMAND_DESCRIPTORS",
    "TelegramMarketCommandsMixin",
    "SystemCommandDescriptor",
    "SYSTEM_COMMAND_DESCRIPTORS",
    "TelegramSystemCommandsMixin",
    "TelegramAdminCommandsMixin",
    "TelegramCallbackHandlerMixin",
    "TelegramMediaHandlerMixin",
]
