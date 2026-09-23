import pytest
from unittest.mock import MagicMock, patch
import os
from telegram_bot.command_router import CommandRouter, CommandType, ParsedCommand

class TestCommandRouter:
    @patch.dict(os.environ, {"TELEGRAM_ADMIN_CHAT_ID": "123", "TELEGRAM_ALLOWED_USERS": "123,456"})
    def test_init_from_env(self):
        router = CommandRouter()
        assert router.admin_chat_id == 123
        assert router.allowed_user_ids == {123, 456}

    @patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "", "TELEGRAM_ADMIN_CHAT_ID": ""}, clear=False)
    def test_is_authorized(self):
        router = CommandRouter(admin_chat_id=123, allowed_user_ids={123, 456})
        assert router.is_authorized(123)
        assert router.is_authorized(456)
        assert not router.is_authorized(789)

        # When only admin_chat_id is given and env has no ALLOWED_USERS,
        # router defaults to admin-only whitelist
        router2 = CommandRouter(admin_chat_id=123)
        assert router2.is_authorized(123)
        assert not router2.is_authorized(456)

    def test_parse_no_message(self):
        router = CommandRouter(admin_chat_id=123)
        update = MagicMock()
        update.message = None
        assert router.parse(update) is None
        
        update.message = MagicMock()
        update.message.text = ""
        assert router.parse(update) is None

    def test_parse_unauthorized(self):
        router = CommandRouter(admin_chat_id=123)
        update = MagicMock()
        update.message.text = "/status"
        update.effective_user.id = 999
        assert router.parse(update) is None

    @patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "", "TELEGRAM_ADMIN_CHAT_ID": ""}, clear=False)
    def test_parse_known_command(self):
        router = CommandRouter(admin_chat_id=123)
        update = MagicMock()
        update.message.text = "/status"
        update.effective_user.id = 123

        parsed = router.parse(update)
        assert parsed is not None
        assert parsed.command == "status"
        assert parsed.command_type == CommandType.DIRECT
        assert not parsed.requires_admin
        assert parsed.args == []

    @patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "", "TELEGRAM_ADMIN_CHAT_ID": ""}, clear=False)
    def test_parse_admin_command_allowed(self):
        router = CommandRouter(admin_chat_id=123)
        update = MagicMock()
        update.message.text = "/kill"
        update.effective_user.id = 123

        parsed = router.parse(update)
        assert parsed is not None
        assert parsed.command == "kill"
        assert parsed.command_type == CommandType.ADMIN
        assert parsed.requires_admin

    def test_parse_admin_command_denied(self):
        router = CommandRouter(admin_chat_id=123, allowed_user_ids={123, 456})
        update = MagicMock()
        update.message.text = "/kill"
        update.effective_user.id = 456
        
        parsed = router.parse(update)
        assert parsed is not None
        assert parsed.command == "_unauthorized_admin"
        assert parsed.requires_admin

    @patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "", "TELEGRAM_ADMIN_CHAT_ID": ""}, clear=False)
    def test_parse_unknown_command(self):
        router = CommandRouter(admin_chat_id=123)
        update = MagicMock()
        update.message.text = "/unknown_cmd"
        update.effective_user.id = 123

        parsed = router.parse(update)
        assert parsed.command == "chat"
        assert parsed.command_type == CommandType.CHAT

    @patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "", "TELEGRAM_ADMIN_CHAT_ID": ""}, clear=False)
    def test_parse_chat(self):
        router = CommandRouter(admin_chat_id=123)
        update = MagicMock()
        update.message.text = "Hello Claude"
        update.effective_user.id = 123

        parsed = router.parse(update)
        assert parsed.command == "chat"
        assert parsed.command_type == CommandType.CHAT
        assert parsed.raw_text == "Hello Claude"

    def test_build_help_text(self):
        text = CommandRouter.build_help_text()
        assert "Monika" in text
        assert "AI Trading Agent" in text
        assert "/status" in text
        assert "/fedwatch" in text
        assert "/yields" in text
        assert "/fear_greed" in text
        assert "/cot" in text

    def test_keyboards(self):
        kb1 = CommandRouter.build_confirm_keyboard("act123")
        assert kb1.inline_keyboard[0][0].callback_data == "confirm:act123"
        
        kb2 = CommandRouter.build_close_keyboard(999)
        assert kb2.inline_keyboard[0][0].callback_data == "close:999"

    def test_parse_market_intelligence_commands(self):
        router = CommandRouter(admin_chat_id=123, allowed_user_ids={123})
        for cmd in ["fedwatch", "yields", "fear_greed", "cot"]:
            update = MagicMock()
            update.message.text = f"/{cmd}"
            update.effective_user.id = 123
            parsed = router.parse(update)
            assert parsed is not None
            assert parsed.command == cmd
            assert parsed.command_type == CommandType.DIRECT
            assert not parsed.requires_admin

    def test_parse_playbook_and_skill_commands(self):
        router = CommandRouter(admin_chat_id=123, allowed_user_ids={123})
        # playbooks & crystallized are direct
        for cmd in ["playbooks", "crystallized"]:
            update = MagicMock()
            update.message.text = f"/{cmd}"
            update.effective_user.id = 123
            parsed = router.parse(update)
            assert parsed is not None
            assert parsed.command == cmd
            assert parsed.command_type == CommandType.DIRECT
            assert not parsed.requires_admin

        # rollback is admin
        update = MagicMock()
        update.message.text = "/rollback eurusd_trend"
        update.effective_user.id = 123
        parsed = router.parse(update)
        assert parsed is not None
        assert parsed.command == "rollback"
        assert parsed.args == ["eurusd_trend"]
        assert parsed.command_type == CommandType.ADMIN
        assert parsed.requires_admin


