"""
Unit tests for modular telegram command descriptors and routing (telegram_bot/handlers/).
"""

import pytest
from telegram_bot.handlers import (
    TRADING_COMMAND_DESCRIPTORS,
    MARKET_COMMAND_DESCRIPTORS,
    SYSTEM_COMMAND_DESCRIPTORS,
)
from telegram_bot.command_router import DIRECT_COMMANDS


def test_trading_command_descriptors_integrity():
    assert "pause" in TRADING_COMMAND_DESCRIPTORS
    assert "kill" in TRADING_COMMAND_DESCRIPTORS
    assert "resume" in TRADING_COMMAND_DESCRIPTORS
    assert TRADING_COMMAND_DESCRIPTORS["pause"].admin_only is True
    assert TRADING_COMMAND_DESCRIPTORS["kill"].admin_only is True
    assert TRADING_COMMAND_DESCRIPTORS["orders"].admin_only is False


def test_market_command_descriptors_integrity():
    assert "status" in MARKET_COMMAND_DESCRIPTORS
    assert "positions" in MARKET_COMMAND_DESCRIPTORS
    assert "vix" in MARKET_COMMAND_DESCRIPTORS
    assert "brief" in MARKET_COMMAND_DESCRIPTORS
    assert MARKET_COMMAND_DESCRIPTORS["status"].admin_only is False


def test_system_command_descriptors_integrity():
    assert "start" in SYSTEM_COMMAND_DESCRIPTORS
    assert "help" in SYSTEM_COMMAND_DESCRIPTORS
    assert "stats" in SYSTEM_COMMAND_DESCRIPTORS
    assert "backtest" in SYSTEM_COMMAND_DESCRIPTORS
    assert SYSTEM_COMMAND_DESCRIPTORS["backtest"].admin_only is True


def test_cross_consistency_with_direct_commands():
    # Verify critical admin commands in descriptors match DIRECT_COMMANDS registry
    for name, desc in TRADING_COMMAND_DESCRIPTORS.items():
        if name in DIRECT_COMMANDS:
            assert desc.admin_only == DIRECT_COMMANDS[name]["admin_only"]
