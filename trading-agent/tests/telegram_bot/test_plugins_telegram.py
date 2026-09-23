# ==============================================================================
# File: tests/telegram_bot/test_plugins_telegram.py
# Description: Unit tests for Telegram Bot plugin commands and keyboard builders
# ==============================================================================

import pytest
from unittest.mock import MagicMock, patch
from telegram_bot.bot import TelegramBot
from telegram_bot.command_router import CommandRouter, CommandType


def test_command_router_plugin_commands():
    router = CommandRouter(admin_chat_id=123, allowed_user_ids={123, 456})

    # Non-admin user (456) can run /plugins and /plugin_catalog
    update_plugins = MagicMock()
    update_plugins.message.text = "/plugins"
    update_plugins.effective_user.id = 456
    parsed = router.parse(update_plugins)
    assert parsed is not None
    assert parsed.command == "plugins"
    assert not parsed.requires_admin

    update_catalog = MagicMock()
    update_catalog.message.text = "/plugin_catalog"
    update_catalog.effective_user.id = 456
    parsed = router.parse(update_catalog)
    assert parsed is not None
    assert parsed.command == "plugin_catalog"
    assert not parsed.requires_admin

    # Non-admin user (456) is rejected from /plugin_install and /plugin_toggle
    update_install = MagicMock()
    update_install.message.text = "/plugin_install monika-plugin-deepseek"
    update_install.effective_user.id = 456
    parsed_denied = router.parse(update_install)
    assert parsed_denied is not None
    assert parsed_denied.command == "_unauthorized_admin"
    assert parsed_denied.requires_admin is True

    # Admin user (123) is allowed to run /plugin_install
    update_install.effective_user.id = 123
    parsed_admin = router.parse(update_install)
    assert parsed_admin is not None
    assert parsed_admin.command == "plugin_install"
    assert parsed_admin.requires_admin is True
    assert parsed_admin.args == ["monika-plugin-deepseek"]


def test_telegram_bot_plugin_builders():
    bot = TelegramBot(settings={})
    sample_plugins = [
        {
            "id": "macro_to_asset",
            "name": "Macro To Asset",
            "category": "analysis_pipeline",
            "version": "1.0.0",
            "enabled": True,
            "status": "ACTIVE",
            "description": "Fundamental analysis",
        },
        {
            "id": "technical_scalping",
            "name": "Technical Scalping",
            "category": "analysis_pipeline",
            "version": "1.0.0",
            "enabled": False,
            "status": "DISABLED",
            "description": "Scalping analysis",
        },
    ]

    text = bot._build_plugins_text(sample_plugins)
    assert "MONIKA PLUG-IN HARNESS" in text
    assert "Macro To Asset" in text
    assert "Technical Scalping" in text
    assert "🟢" in text
    assert "⚪" in text

    markup = bot._build_plugins_keyboard(sample_plugins)
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    btn_texts = [btn.text for btn in buttons]
    callbacks = [btn.callback_data for btn in buttons]

    assert any("🟢" in t and "Macro To Asset" in t for t in btn_texts)
    assert any("⚪" in t and "Technical" in t for t in btn_texts)
    assert any("plg:t:macro_to_asset" in c for c in callbacks)
    assert any("plg:cat" in c for c in callbacks)
    assert any("plg:ref" in c for c in callbacks)
