"""
Telegram Bot Handlers Package.
Provides modular command descriptors, categories, and routing maps.
"""
from monika.interfaces.telegram.handlers.trading_commands import (
    CommandDescriptor,
    TRADING_COMMAND_DESCRIPTORS,
    execute_trading_command,
)
from monika.interfaces.telegram.handlers.market_commands import (
    MarketCommandDescriptor,
    MARKET_COMMAND_DESCRIPTORS,
)
from monika.interfaces.telegram.handlers.system_commands import (
    SystemCommandDescriptor,
    SYSTEM_COMMAND_DESCRIPTORS,
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
