import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import os
from utils.infra.notifier import AgentNotifier

class TestNotifier:
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_ADMIN_CHAT_ID": "123"})
    @patch("utils.infra.notifier.Bot")
    def test_init(self, mock_bot):
        notifier = AgentNotifier()
        assert notifier.token == "test_token"
        assert notifier.admin_id == "123"
        mock_bot.assert_called_with(token="test_token")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_ADMIN_CHAT_ID": "123"})
    @patch("utils.infra.notifier.Bot")
    async def test_send_messages(self, mock_bot):
        notifier = AgentNotifier()
        notifier.bot.send_message = AsyncMock()

        await notifier.send_critical("Crit")
        notifier.bot.send_message.assert_called_with(chat_id="123", text="🚨 <b>CRITICAL ERROR</b> 🚨\nCrit", parse_mode="HTML")

        await notifier.send_warning("Warn")
        notifier.bot.send_message.assert_called_with(chat_id="123", text="⚠️ <b>WARNING</b> ⚠️\nWarn", parse_mode="HTML")

        await notifier.send_info("Info")
        notifier.bot.send_message.assert_called_with(chat_id="123", text="ℹ️ <b>INFO</b>\nInfo", parse_mode="HTML")

        await notifier.send("Custom HTML Direct Message")
        notifier.bot.send_message.assert_called_with(chat_id="123", text="Custom HTML Direct Message", parse_mode="HTML")

        await notifier.send_alert("System degraded")
        notifier.bot.send_message.assert_called_with(chat_id="123", text="⚠️ <b>WARNING</b> ⚠️\nSystem degraded", parse_mode="HTML")

        summary = {
            "elapsed_total_s": 10.5,
            "api_cost_usd": 0.05,
            "per_asset": {
                "BTCUSD": {"decision": "buy", "confidence": 0.8},
                "USDJPY": {"decision": "skip", "confidence": 0.0, "skipped_by_cooldown": True}
            }
        }
        await notifier.send_cycle_summary(summary)
        call_args = notifier.bot.send_message.call_args[1]
        assert "CYCLE COMPLETE" in call_args["text"]
        assert "10.5s" in call_args["text"]
        assert "BTCUSD: BUY (conf: 0.80)" in call_args["text"]
        assert "USDJPY: SKIP (cooldown)" in call_args["text"]

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_ADMIN_ID": "456", "TELEGRAM_ADMIN_CHAT_ID": ""}, clear=False)
    @patch("utils.infra.notifier.Bot")
    def test_old_env_var_does_not_work(self, mock_bot):
        """Verify that old TELEGRAM_ADMIN_ID env var no longer works (migration test)."""
        notifier = AgentNotifier()
        # TELEGRAM_ADMIN_CHAT_ID cleared — admin_id should be None
        assert notifier.admin_id is None

    @patch.dict(os.environ, {}, clear=True)
    @patch("utils.infra.notifier.Bot", side_effect=Exception("No token"))
    def test_init_no_token(self, mock_bot):
        """AgentNotifier should handle missing token gracefully."""
        notifier = AgentNotifier()
        assert notifier.bot is None


def test_sanitize_telegram_html():
    from utils.infra.notifier import sanitize_telegram_html

    # Valid tags must be preserved
    text = "<b>Bold</b> <code>Code</code> <i>Italic</i> <a href='https://example.com'>Link</a>"
    assert sanitize_telegram_html(text) == text

    # Comparison operators and unescaped entities must be escaped
    raw_alert = (
        "💡 <b>Autonomous Strategy Synthesized & Deployed!</b>\n"
        "<b>ID:</b> <code>alpha_xauusd_5044bf</code>\n"
        "<b>Sharpe:</b> <code>2.88</code> (Target > 1.5)\n"
        "<b>Max Drawdown:</b> <code>2.3%</code> (Limit < 10.0%)\n"
        "Registered for live & paper execution."
    )
    sanitized = sanitize_telegram_html(raw_alert)
    assert "<b>Sharpe:</b> <code>2.88</code> (Target &gt; 1.5)" in sanitized
    assert "<b>Max Drawdown:</b> <code>2.3%</code> (Limit &lt; 10.0%)" in sanitized
    assert "<b>ID:</b> <code>alpha_xauusd_5044bf</code>" in sanitized
    assert "live &amp; paper" in sanitized
    # No standalone '< ' that crashes Telegram HTML parser
    assert "< 10.0%" not in sanitized
