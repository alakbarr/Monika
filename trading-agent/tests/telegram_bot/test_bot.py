import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import os
from telegram_bot.bot import TelegramBot

class TestTelegramBot:
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test", "TELEGRAM_ADMIN_CHAT_ID": "123", "TELEGRAM_ALLOWED_USERS": "123,456"})
    @patch("telegram_bot.bot.ApplicationBuilder")
    def test_init(self, mock_builder):
        bot = TelegramBot({})
        assert bot.token == "123:test"
        assert bot.admin_chat_id == 123
        assert bot.allowed_user_ids == {123, 456}
        mock_builder.return_value.token.assert_called_with("123:test")
        
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_ADMIN_CHAT_ID": "123"})
    def test_init_no_token(self):
        bot = TelegramBot({})
        assert bot._app is None

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test", "TELEGRAM_ADMIN_CHAT_ID": "123"})
    @patch("telegram_bot.bot.ApplicationBuilder")
    async def test_start(self, mock_builder):
        mock_app = AsyncMock()
        mock_app.__aenter__ = AsyncMock(return_value=mock_app)
        mock_app.__aexit__ = AsyncMock(return_value=None)
        mock_app.start = AsyncMock()
        mock_app.initialize = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app.updater.start_polling = AsyncMock()
        mock_app.updater.stop = AsyncMock()
        mock_builder.return_value.token.return_value.build.return_value = mock_app
        
        bot = TelegramBot({})
        
        # We need to cancel the task after a short delay since it blocks forever
        import asyncio
        async def run_and_cancel():
            task = asyncio.create_task(bot.start())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
        await run_and_cancel()
        mock_app.start.assert_called_once()
        mock_app.updater.start_polling.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification(self):
        bot = TelegramBot({})
        bot._app = MagicMock()
        bot.admin_chat_id = 123
        bot._is_running = True
        bot._app.bot.send_message = AsyncMock()
        
        await bot.send_notification("Test msg")
        bot._app.bot.send_message.assert_called_once()
        assert bot._app.bot.send_message.call_args[1]["chat_id"] == 123
        assert bot._app.bot.send_message.call_args[1]["text"] == "Test msg"

    @pytest.mark.asyncio
    async def test_auth_guards(self):
        bot = TelegramBot({})
        bot._router = MagicMock()
        update = MagicMock()
        update.effective_user.id = 123
        
        bot._router.is_authorized.return_value = True
        assert bot._is_authorized(update) is True
        
        bot._router.is_admin.return_value = False
        assert bot._is_admin(update) is False

        update.message.reply_text = AsyncMock()
        await bot._reject_non_admin(update)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_start_and_help(self):
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        
        await bot._cmd_start(update, MagicMock())
        update.message.reply_text.assert_called_once()
        
        update.message.reply_text.reset_mock()
        await bot._cmd_help(update, MagicMock())
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_status_positions_brief_history_risk_vix(self):
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)
        
        # Mock builders
        bot._build_status_text = AsyncMock(return_value="status")
        bot._build_positions_text = AsyncMock(return_value="positions")
        bot._build_brief_text = AsyncMock(return_value="brief")
        bot._build_history_text = AsyncMock(return_value="history")
        bot._build_risk_text = AsyncMock(return_value="risk")
        bot._build_vix_text = AsyncMock(return_value="vix")
        
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.message.chat.send_action = AsyncMock()
        ctx = MagicMock()
        
        await bot._cmd_status(update, ctx)
        await bot._cmd_positions(update, ctx)
        await bot._cmd_brief(update, ctx)
        await bot._cmd_history(update, ctx)
        await bot._cmd_risk(update, ctx)
        await bot._cmd_vix(update, ctx)
        
        assert update.message.reply_text.call_count == 6

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    @patch("risk.risk_gate.RiskGate")
    async def test_cmd_pause_resume(self, mock_risk_gate_cls, mock_get_session):
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)
        bot._is_admin = MagicMock(return_value=True)
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_exec_res
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        mock_risk_gate = mock_risk_gate_cls.return_value
        mock_risk_gate.pause_trading = AsyncMock()
        mock_risk_gate.resume_trading = AsyncMock()
        
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        ctx = MagicMock()
        ctx.args = ["maintenance", "-y"]
        
        await bot._cmd_pause(update, ctx)
        mock_risk_gate.pause_trading.assert_called_once()
        
        await bot._cmd_resume(update, ctx)
        mock_risk_gate.resume_trading.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_kill_close_run_backtest(self):
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)
        bot._is_admin = MagicMock(return_value=True)
        
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        ctx = MagicMock()
        
        await bot._cmd_kill(update, ctx)
        assert update.message.reply_text.call_count == 1
        
        ctx.args = ["123"]
        await bot._cmd_close(update, ctx)
        assert update.message.reply_text.call_count == 2
        
        await bot._cmd_run(update, ctx)
        # without cycle_scheduler, it prints 2 messages
        assert update.message.reply_text.call_count == 4
        
        await bot._cmd_backtest(update, ctx)
        assert update.message.reply_text.call_count == 5

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_handle_chat(self, mock_get_session):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)
        
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.message.chat.send_action = AsyncMock()
        update.effective_user.id = 123
        
        mock_agent = MagicMock()
        from datetime import datetime, timezone
        mock_agent.last_active = datetime.now(timezone.utc)
        mock_agent.handle = AsyncMock(return_value=("Test reply", MagicMock(description="Action", action_id="1")))
        bot._chat_agents[123] = mock_agent
        
        await bot._handle_chat(update, MagicMock())
        assert update.message.reply_text.call_count == 2 # 1 for reply, 1 for proposed action

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_handle_callback(self, mock_get_session):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)
        bot._is_admin = MagicMock(return_value=True)
        
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        
        # Test cancel
        update.callback_query.data = "cancel"
        await bot._handle_callback(update, MagicMock())
        update.callback_query.edit_message_text.assert_called_with("❌ Dibatalkan.")
        
        # Test confirm
        update.callback_query.data = "confirm:1"
        update.effective_user.id = 123
        mock_agent = MagicMock()
        mock_agent.confirm_action = AsyncMock(return_value=(True, "Success"))
        mock_agent.approve_for_session = AsyncMock(return_value=(True, "Session approved"))
        mock_agent._pending_actions = {"1": MagicMock()}
        bot._chat_agents[123] = mock_agent
        await bot._handle_callback(update, MagicMock())
        update.callback_query.edit_message_text.assert_called_with("Success")

        # Test allow_session
        update.callback_query.data = "allow_session:1"
        await bot._handle_callback(update, MagicMock())
        mock_agent.approve_for_session.assert_called_once_with("1")
        update.callback_query.edit_message_text.assert_called_with("Session approved")

    def test_chunk_text(self):
        bot = TelegramBot({})
        text = "a" * 5000
        chunks = bot._chunk_text(text, 4000)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4000
        assert len(chunks[1]) == 1000

    def test_chunk_text_markdown_code_block_balancing(self):
        bot = TelegramBot({})
        code_body = "x = 1\n" * 300  # ~1800 chars
        text = f"```python\n{code_body}```"
        chunks = bot._chunk_text(text, max_len=1000)
        assert len(chunks) >= 2
        # Verify every chunk has balanced triple backticks
        for i, chunk in enumerate(chunks):
            assert chunk.count("```") % 2 == 0, f"Chunk {i} has unbalanced code block: {chunk}"

    def test_chunk_text_markdown_bold_and_italic_balancing(self):
        bot = TelegramBot({})
        bold_text = "*" + ("important words " * 200) + "*"
        chunks = bot._chunk_text(bold_text, max_len=1000)
        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            assert chunk.count("*") % 2 == 0, f"Chunk {i} has unbalanced bold asterisks: {chunk}"

    def test_chunk_text_single_short_message_unclosed_entity_balancing(self):
        """Memverifikasi bahwa pesan pendek (<4000 karakter) yang memiliki tag unclosed tetap diseimbangkan."""
        bot = TelegramBot({})
        # Unclosed code block
        assert bot._chunk_text("```python\nprint('hello')")[0].endswith("```")
        # Unclosed bold
        assert bot._chunk_text("Hasil analisis: *BULLISH")[0] == "Hasil analisis: *BULLISH*"
        # Unclosed italic
        assert bot._chunk_text("Status: _ACTIVE")[0] == "Status: _ACTIVE_"
        # Unclosed inline code
        assert bot._chunk_text("Variable `USD_JPY")[0] == "Variable `USD_JPY`"

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_cmd_tearsheet(self, mock_get_session):
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)

        mock_session = AsyncMock()
        mock_result = MagicMock()

        from datetime import datetime, timezone
        from database.models import PaperTradeRecord
        mock_trade = MagicMock(spec=PaperTradeRecord)
        mock_trade.symbol = "EURUSD"
        mock_trade.pnl_usd = 150.0
        mock_trade.pnl_pct = 1.5
        mock_trade.closed_at = datetime.now(timezone.utc)
        mock_result.scalars.return_value.all.return_value = [mock_trade]

        mock_session.execute.return_value = mock_result
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.message.chat.send_action = AsyncMock()
        ctx = MagicMock()
        ctx.args = ["14"]

        await bot._cmd_tearsheet(update, ctx)
        assert update.message.reply_text.call_count >= 1
        call_args = update.message.reply_text.call_args[0][0]
        assert "Executive Quant Tearsheet" in call_args



