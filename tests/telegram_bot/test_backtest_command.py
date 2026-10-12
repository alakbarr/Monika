# ==============================================================================
# File: tests/telegram_bot/test_backtest_command.py
# ==============================================================================

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram_bot.bot import TelegramBot


@pytest.fixture
def mock_bot():
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test", "TELEGRAM_ADMIN_CHAT_ID": "123"}):
        with patch("telegram_bot.bot.ApplicationBuilder"):
            bot = TelegramBot({})
            bot._is_authorized = MagicMock(return_value=True)
            bot._is_admin = MagicMock(return_value=True)
            return bot


def make_update(user_id=123):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def make_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


@pytest.mark.asyncio
async def test_cmd_backtest_default_days(mock_bot):
    update = make_update()
    ctx = make_context([])

    with patch.object(mock_bot, "_run_backtest_and_notify", new_callable=AsyncMock) as mock_run:
        await mock_bot._cmd_backtest(update, ctx)
        # Give asyncio.create_task a moment to invoke mock_run
        await asyncio.sleep(0.01)

        update.message.reply_text.assert_awaited_once()
        call_msg = update.message.reply_text.await_args[0][0]
        assert "Memulai Point-in-Time Backtest (30 hari)" in call_msg
        mock_run.assert_awaited_once_with(update, 30)


@pytest.mark.asyncio
async def test_cmd_backtest_custom_days(mock_bot):
    update = make_update()
    ctx = make_context(["45"])

    with patch.object(mock_bot, "_run_backtest_and_notify", new_callable=AsyncMock) as mock_run:
        await mock_bot._cmd_backtest(update, ctx)
        await asyncio.sleep(0.01)

        update.message.reply_text.assert_awaited_once()
        call_msg = update.message.reply_text.await_args[0][0]
        assert "Memulai Point-in-Time Backtest (45 hari)" in call_msg
        mock_run.assert_awaited_once_with(update, 45)


@pytest.mark.asyncio
async def test_cmd_backtest_invalid_number(mock_bot):
    update = make_update()
    ctx = make_context(["invalid"])

    with patch.object(mock_bot, "_run_backtest_and_notify", new_callable=AsyncMock) as mock_run:
        await mock_bot._cmd_backtest(update, ctx)
        await asyncio.sleep(0.01)

        update.message.reply_text.assert_awaited_once()
        call_msg = update.message.reply_text.await_args[0][0]
        assert "Format salah" in call_msg
        mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_backtest_out_of_bounds(mock_bot):
    update = make_update()
    ctx = make_context(["999"])

    with patch.object(mock_bot, "_run_backtest_and_notify", new_callable=AsyncMock) as mock_run:
        await mock_bot._cmd_backtest(update, ctx)
        await asyncio.sleep(0.01)

        update.message.reply_text.assert_awaited_once()
        call_msg = update.message.reply_text.await_args[0][0]
        assert "harus antara 1 dan 365" in call_msg
        mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_run_backtest_and_notify_success(mock_bot):
    update = make_update()

    mock_record = MagicMock()
    mock_record.initial_equity = 10000.0
    mock_record.final_equity = 10500.0
    mock_record.total_trades = 5
    mock_record.win_rate = 60.0

    mock_trade1 = MagicMock()
    mock_trade1.symbol = "XAUUSD"
    mock_trade1.pnl_pct = 2.5

    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(return_value=mock_record)
    mock_engine.trades = [mock_trade1]

    with patch("backtest.point_in_time_engine.PointInTimeBacktestEngine", return_value=mock_engine):
        await mock_bot._run_backtest_and_notify(update, 30)

        update.message.reply_text.assert_awaited_once()
        call_msg = update.message.reply_text.await_args[0][0]
        assert "Backtest 30 hari Selesai" in call_msg
        assert "Total trades: 5" in call_msg
        assert "Win rate: 60.00%" in call_msg
        assert "+5.00%" in call_msg
