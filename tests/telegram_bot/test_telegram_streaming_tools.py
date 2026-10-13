# ==============================================================================
# File: tests/telegram_bot/test_telegram_streaming_tools.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from monika.interfaces.telegram.bot import TelegramBot
from monika.interfaces.telegram.chat_agent import ChatAgent


def test_telegram_bot_html_chunk_balancing():
    # Test that unclosed tags in HTML chunk are closed and reopened
    raw_html = "<b>Hello <i>World and <code>sample code"
    balanced, resume = TelegramBot._balance_html_chunk(raw_html)
    assert balanced.endswith("</code></i></b>")
    assert resume == "<b><i><code>"


def test_telegram_bot_chunk_text_html():
    long_content = "<b>" + ("word " * 1000) + "</b>"
    chunks = TelegramBot._chunk_text(long_content, max_len=1000, is_html=True)
    assert len(chunks) > 1
    # First chunk should have closing tag
    assert chunks[0].endswith("</b>")
    # Second chunk should have reopening tag
    assert chunks[1].startswith("<b>")


@pytest.mark.asyncio
async def test_chat_agent_streaming_routes_tools():
    settings = {
        "trading": {"symbols": ["XAUUSD", "EURUSD"]},
        "llm": {"provider": "gemini"},
        "telegram": {"streaming": True},
    }

    agent = ChatAgent(settings=settings, user_id=12345, is_admin=True)

    # Mock _handle_internal to verify it gets called when query needs tools
    mock_pending = MagicMock()
    mock_pending.action_id = "act_999"
    mock_pending.description = "Test trade proposal"

    agent._handle_internal = AsyncMock(return_value=("Posisi Anda saat ini: 0 open.", mock_pending))
    agent._stream_response = AsyncMock(return_value="Posisi Anda saat ini: 0 open.")

    update = MagicMock()
    context = MagicMock()

    # Query with tool intent: 'cek posisi'
    reply, pending = await agent._handle_streaming(
        update=update,
        context=context,
        user_message="Tolong cek posisi trading saya sekarang",
    )

    assert agent._handle_internal.called
    assert reply == "Posisi Anda saat ini: 0 open."
    assert pending == mock_pending
    assert agent.was_last_turn_streamed is True


@pytest.mark.asyncio
async def test_telegram_bot_cmd_orders():
    bot = TelegramBot(settings={}, execution_service=None)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat = MagicMock()
    update.message.chat.send_action = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    bot.allowed_user_ids.add(12345)

    ctx = MagicMock()
    ctx.args = []

    with patch("monika.infrastructure.brokers.mt5_client._get_orders", return_value=[]):
        await bot._cmd_orders(update, ctx)
        update.message.reply_text.assert_called_once()
        call_arg = update.message.reply_text.call_args[0][0]
        assert "Tidak ada pending order" in call_arg
