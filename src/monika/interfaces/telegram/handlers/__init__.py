"""
Telegram Bot Handlers Package.
Provides modular command descriptors, categories, and routing maps.
"""

from monika.interfaces.telegram.handlers.market_commands import (
    MARKET_COMMAND_DESCRIPTORS,
    MarketCommandDescriptor,
)
from monika.interfaces.telegram.handlers.system_commands import (
    SYSTEM_COMMAND_DESCRIPTORS,
    SystemCommandDescriptor,
)
from monika.interfaces.telegram.handlers.trading_commands import (
    TRADING_COMMAND_DESCRIPTORS,
    CommandDescriptor,
    execute_trading_command,
)

__all__ = [
    "CommandDescriptor",
    "TRADING_COMMAND_DESCRIPTORS",
    "execute_trading_command",
    "MarketCommandDescriptor",
    "MARKET_COMMAND_DESCRIPTORS",
    "SystemCommandDescriptor",
    "SYSTEM_COMMAND_DESCRIPTORS",
]
