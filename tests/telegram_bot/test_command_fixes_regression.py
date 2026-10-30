"""
Unit and regression tests for command execution across Telegram, CLI Chat, and TUI channels.
Verifies fixes for /help chunking, unauthorized response, registry sync, argument resilience,
CLI Chat API v1 paths, and TUI RBAC action headers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User, Message, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.command_router import (
    CommandRouter,
    DIRECT_COMMANDS,
    COMMAND_HELP,
    CommandType,
)
from monika.interfaces.telegram.handlers.system_commands import TelegramSystemCommandsMixin
from monika.interfaces.telegram.handlers.admin_commands import TelegramAdminCommandsMixin
from monika.interfaces.telegram.handlers.market_commands import TelegramMarketCommandsMixin
from monika.interfaces.telegram.formatters.text_builders import TelegramFormatterMixin
from monika.interfaces.cli.chat.commands import ChatCommandRouter
from monika.interfaces.cli.chat.prompt import ChatPromptManager
from monika.interfaces.cli.chat.renderer import ChatRenderer
from monika.interfaces.cli.tui_app.mixins.actions import ActionsMixin


# ==============================================================================
# Telegram /help and System Commands Tests
# ==============================================================================


class DummySystemBot(TelegramSystemCommandsMixin, TelegramFormatterMixin):
    def __init__(self, authorized: bool = True):
        self._authorized = authorized
        self._reject_called = False

    def _is_authorized(self, update: Update) -> bool:
        return self._authorized

    async def _reject_unauthorized(self, update: Update) -> None:
        self._reject_called = True


@pytest.mark.asyncio
async def test_cmd_help_unauthorized_replies_guidance():
    bot = DummySystemBot(authorized=False)
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    update.message = message
    user = MagicMock(spec=User)
    user.id = 999888
    update.effective_user = user
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    await bot._cmd_help(update, ctx)

    assert not bot._reject_called
    message.reply_text.assert_called_once()
    reply_call = message.reply_text.call_args
    assert "999888" in reply_call[0][0]
    assert "/start" in reply_call[0][0] or "/pair" in reply_call[0][0]


@pytest.mark.asyncio
async def test_cmd_help_authorized_balanced_chunks():
    bot = DummySystemBot(authorized=True)
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    update.message = message
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    await bot._cmd_help(update, ctx)

    assert message.reply_text.called
    chunks_sent = [call[0][0] for call in message.reply_text.call_args_list]
    for chunk in chunks_sent:
        assert chunk.count("```") % 2 == 0, "Code blocks must be balanced in all chunks"


@pytest.mark.asyncio
async def test_cmd_help_markdown_error_fallback_to_plain():
    bot = DummySystemBot(authorized=True)
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    update.message = message
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # First call with parse_mode raises, second call (plain) succeeds
    call_count = 0

    async def fake_reply(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if "parse_mode" in kwargs:
            raise Exception("Telegram entity parse error")
        return MagicMock()

    message.reply_text.side_effect = fake_reply

    await bot._cmd_help(update, ctx)

    # Should have attempted markdown, caught exception, and fallen back to plain text
    assert call_count >= 2


# ==============================================================================
# Telegram Direct Commands Registry Tests
# ==============================================================================


def test_telegram_direct_commands_registered():
    for cmd in ["orders", "chart", "smc", "factors", "alpha"]:
        assert cmd in DIRECT_COMMANDS, f"{cmd} must be in DIRECT_COMMANDS"
        assert DIRECT_COMMANDS[cmd]["admin_only"] is False
        assert DIRECT_COMMANDS[cmd]["type"] == CommandType.DIRECT
        assert cmd in COMMAND_HELP, f"{cmd} must be in COMMAND_HELP"


def test_command_router_parses_new_direct_commands():
    router = CommandRouter(admin_chat_id=123, allowed_user_ids={123})

    for cmd in ["/orders", "/chart EURUSD", "/smc XAUUSD", "/factors USDJPY", "/alpha EURUSD alpha_001"]:
        update = MagicMock(spec=Update)
        message = MagicMock(spec=Message)
        message.text = cmd
        update.message = message
        user = MagicMock(spec=User)
        user.id = 123
        update.effective_user = user
        chat = MagicMock(spec=Chat)
        chat.id = 123
        update.effective_chat = chat

        parsed = router.parse(update)
        assert parsed is not None
        assert parsed.command_type == CommandType.DIRECT


# ==============================================================================
# Telegram Admin & Market Commands Argument Resilience Tests
# ==============================================================================


class DummyAdminBot(TelegramAdminCommandsMixin):
    def _is_authorized(self, update: Update) -> bool:
        return True


class DummyMarketBot(TelegramMarketCommandsMixin):
    def _is_authorized(self, update: Update) -> bool:
        return True


@pytest.mark.asyncio
async def test_cmd_chronicle_invalid_year_resilience():
    bot = DummyAdminBot()
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    message.chat = AsyncMock(spec=Chat)
    update.message = message
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.args = ["Jan", "not_a_year"]

    await bot._cmd_chronicle(update, ctx)

    message.reply_text.assert_called_once()
    assert "tidak valid" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_counterfactual_invalid_trade_id_resilience():
    bot = DummyAdminBot()
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    message.chat = AsyncMock(spec=Chat)
    update.message = message
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.args = ["invalid_trade_id"]

    await bot._cmd_counterfactual(update, ctx)

    message.reply_text.assert_called_once()
    assert "Usage: `/counterfactual" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_alpha_unknown_factor_resilience():
    bot = DummyMarketBot()
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    message.chat = AsyncMock(spec=Chat)
    update.message = message
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.args = ["EURUSD", "non_existent_factor_xyz"]

    with (
        patch("monika.domain.indicators.micro_alpha_zoo.MicroAlphaZoo.compute_factor") as mock_compute,
        patch("monika.infrastructure.database.db.get_session") as mock_db,
    ):
        mock_compute.side_effect = KeyError("Alpha factor not found")
        sess_mock = AsyncMock()
        mock_db.return_value.__aenter__.return_value = sess_mock
        res_mock = MagicMock()
        res_mock.scalars.return_value.all.return_value = [
            MagicMock(open=1.0, high=1.1, low=0.9, close=1.05, volume=100)
        ]
        sess_mock.execute = AsyncMock(return_value=res_mock)

        await bot._cmd_alpha(update, ctx)

        message.reply_text.assert_called_once()
        assert "tidak ditemukan" in message.reply_text.call_args[0][0]


# ==============================================================================
# CLI Chat Commands Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_cli_chat_commands_paths_and_auth():
    renderer = MagicMock(spec=ChatRenderer)
    renderer.console = MagicMock()
    renderer.palette = MagicMock()
    prompt_mgr = MagicMock(spec=ChatPromptManager)
    prompt_mgr.active_mode = "PAPER"
    prompt_mgr.active_model = "fast"

    router = ChatCommandRouter(
        renderer=renderer,
        prompt_manager=prompt_mgr,
        api_url="http://127.0.0.1:8000",
        api_key="secret_test_key",
    )

    # 1. Test /status queries /api/v1/health with auth headers
    with patch("aiohttp.ClientSession") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value.__aenter__.return_value = session
        resp = MagicMock(status=200)
        resp.json = AsyncMock(return_value={"uptime_seconds": 120, "db_connected": True, "mt5_connected": True})
        session.get.return_value.__aenter__.return_value = resp

        await router.handle("/status")
        get_call = session.get.call_args
        assert get_call[0][0] == "http://127.0.0.1:8000/api/v1/health"
        assert get_call[1]["headers"]["X-API-Key"] == "secret_test_key"
        assert get_call[1]["headers"]["Authorization"] == "Bearer secret_test_key"

    # 2. Test /positions queries /api/v1/positions and parses dict-wrapped response
    with patch("aiohttp.ClientSession") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value.__aenter__.return_value = session
        resp = MagicMock(status=200)
        resp.json = AsyncMock(
            return_value={"positions": [{"mt5_ticket": 1234, "symbol": "EURUSD", "direction": "BUY", "pnl": 50.0}]}
        )
        session.get.return_value.__aenter__.return_value = resp

        await router.handle("/positions")
        get_call = session.get.call_args
        assert get_call[0][0] == "http://127.0.0.1:8000/api/v1/positions?status=open"

    # 3. Test /mode calls /api/v1/config/settings
    with patch("aiohttp.ClientSession") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value.__aenter__.return_value = session
        session.put.return_value.__aenter__.return_value = MagicMock(status=200)

        await router.handle("/mode paper")
        put_call = session.put.call_args
        assert put_call[0][0] == "http://127.0.0.1:8000/api/v1/config/settings"

    # 4. Test /cycle sends forced: True
    with patch.object(router, "_post_api", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = (True, "Cycle queued")
        await router.handle("/cycle EURUSD")
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/api/v1/actions/trigger-cycle"
        assert call_args[0][1]["forced"] is True
        assert call_args[0][1]["symbol"] == "EURUSD"


# ==============================================================================
# TUI Actions Mixin RBAC Header & Dynamic URL Tests
# ==============================================================================


class DummyTuiApp(ActionsMixin):
    def __init__(self):
        self.api_url = "http://remote-server:9000"
        self.api_key = "my_tui_secret"
        self._input_focused = False

    def _is_input_focused(self) -> bool:
        return self._input_focused

    def query_one(self, selector, widget_cls=None):
        mock_widget = MagicMock()
        return mock_widget

    async def refresh_data(self):
        pass


@pytest.mark.asyncio
async def test_tui_action_pause_and_resume_headers():
    app = DummyTuiApp()

    with (
        patch("aiohttp.ClientSession") as mock_session_cls,
        patch("monika.application.services.trading_service.TradingService.pause_trading", new_callable=AsyncMock),
        patch("monika.application.services.trading_service.TradingService.resume_trading", new_callable=AsyncMock),
        patch("monika.application.services.trading_service.TradingService.emergency_kill", new_callable=AsyncMock),
        patch("monika.infrastructure.database.db.init_db", new_callable=AsyncMock),
        patch("monika.infrastructure.database.db.get_session"),
    ):
        session = MagicMock()
        mock_session_cls.return_value.__aenter__.return_value = session
        session.post = AsyncMock()

        # Test pause action
        await app.action_pause()
        session_init = mock_session_cls.call_args
        assert session_init[1]["headers"]["X-API-Key"] == "my_tui_secret"
        assert session.post.call_args[0][0] == "http://remote-server:9000/api/v1/actions/pause"

        # Test kill action
        await app._execute_kill()
        assert session.post.call_args[0][0] == "http://remote-server:9000/api/v1/kill"
