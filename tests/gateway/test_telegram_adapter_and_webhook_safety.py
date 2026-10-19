# ==============================================================================
# File: tests/gateway/test_telegram_adapter_and_webhook_safety.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.interfaces.gateway.platforms.telegram_adapter import TelegramPlatformAdapter
from monika.interfaces.gateway.webhook_ingress import normalize_tradingview_payload
from monika.interfaces.telegram.command_router import DIRECT_COMMANDS, CommandType


def test_tradingview_normalization_close_and_fail_closed():
    """Verify TradingView Pine Script alert normalization for exit signals and unknown actions."""
    # 1. Close alert mapping
    close_payload = {"ticker": "EURUSD", "action": "close", "volume": "0.05"}
    norm_close = normalize_tradingview_payload(close_payload)
    assert norm_close["symbol"] == "EURUSD"
    assert norm_close["direction"] == "CLOSE"
    assert norm_close["event_type"] == "close_signal"
    assert norm_close["volume"] == 0.05

    # 2. Exit alert mapping
    exit_payload = {"ticker": "OANDA:XAUUSD", "action": "exit_long"}
    norm_exit = normalize_tradingview_payload(exit_payload)
    assert norm_exit["symbol"] == "XAUUSD"
    assert norm_exit["direction"] == "CLOSE"
    assert norm_exit["event_type"] == "close_signal"

    # 3. Buy alert mapping
    buy_payload = {"ticker": "BTCUSD", "action": "buy", "volume": 0.1}
    norm_buy = normalize_tradingview_payload(buy_payload)
    assert norm_buy["direction"] == "BUY"
    assert norm_buy["event_type"] == "trade_signal"

    # 4. Unknown alert must fail closed (raise ValueError)
    invalid_payload = {"ticker": "EURUSD", "action": "unknown_garbage_signal"}
    with pytest.raises(ValueError, match="Unknown alert action"):
        normalize_tradingview_payload(invalid_payload)


@pytest.mark.asyncio
async def test_telegram_adapter_loop_guard_not_inverted():
    """Verify normal messages are not falsely blocked by BotLoopGuard."""
    adapter = TelegramPlatformAdapter()
    await adapter.start()

    # Provide a dummy message handler
    mock_handler = AsyncMock(return_value="Echo: hello")
    adapter.register_handler(mock_handler)

    # First normal message must succeed (not blocked)
    resp = await adapter.simulate_incoming(chat_id="12345", user_id="user_1", message="Hello Monika")
    assert resp == "Echo: hello"
    assert mock_handler.await_count == 1

    await adapter.stop()


@pytest.mark.asyncio
async def test_telegram_adapter_debounce_resolves_all_futures():
    """Verify burst messages debouncing resolves all pending futures without deadlock."""
    adapter = TelegramPlatformAdapter(debounce_window_s=0.05)
    await adapter.start()

    async def echo_handler(user_id, chat_id, text, meta):
        return f"Echoed: {text}"

    adapter.register_handler(echo_handler)

    # Send 3 rapid messages
    tasks = [
        asyncio.create_task(adapter.handle_debounced_incoming("100", "u1", "msg 1")),
        asyncio.create_task(adapter.handle_debounced_incoming("100", "u1", "msg 2")),
        asyncio.create_task(adapter.handle_debounced_incoming("100", "u1", "msg 3")),
    ]

    results = await asyncio.gather(*tasks)
    assert len(results) == 3
    # All 3 futures must receive the combined flushed output
    for res in results:
        assert res == "Echoed: msg 1\nmsg 2\nmsg 3"

    await adapter.stop()


@pytest.mark.asyncio
async def test_telegram_adapter_send_message_routes_chat_id():
    """Verify send_message forwards explicit target chat_id to bot notification worker."""
    mock_bot = MagicMock()
    mock_bot.send_notification = AsyncMock()

    adapter = TelegramPlatformAdapter()
    adapter.attach_bot_instance(mock_bot)
    await adapter.start()

    sent = await adapter.send_message(target_id="987654", content="Trade alert test")
    assert sent is True
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0]["chat_id"] == "987654"

    # Give event loop a cycle to schedule the background task
    await asyncio.sleep(0.01)
    mock_bot.send_notification.assert_awaited_once_with("Trade alert test", chat_id=987654)

    await adapter.stop()


def test_command_registry_admin_permissions():
    """Verify critical commands require admin role in DIRECT_COMMANDS."""
    assert DIRECT_COMMANDS["cron"]["admin_only"] is True
    assert DIRECT_COMMANDS["cron"]["type"] == CommandType.ADMIN
    assert DIRECT_COMMANDS["model"]["admin_only"] is True
    assert DIRECT_COMMANDS["model"]["type"] == CommandType.ADMIN
