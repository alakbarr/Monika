import asyncio
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_event_loop_is_selector_on_windows():
    """Verify that on Windows the running loop is SelectorEventLoop (required by psycopg)."""
    loop = asyncio.get_running_loop()
    if sys.platform == "win32":
        assert isinstance(loop, asyncio.SelectorEventLoop) or "Selector" in type(loop).__name__, (
            f"Expected SelectorEventLoop for psycopg compatibility, got {type(loop).__name__}"
        )


@pytest.mark.asyncio
async def test_telegram_bot_lifecycle_and_send_notification_resilience():
    """Verify that TelegramBot.send_notification gracefully suppresses errors when bot is stopped."""
    from telegram_bot.bot import TelegramBot

    settings = {"trading": {}}
    bot = TelegramBot(settings)
    
    # 1. Before start, is_running should be False
    assert bot.is_running is False
    
    # 2. send_notification should return early without error when not running
    await bot.send_notification("Test notification before startup")

    # 3. Simulate bot running with mock app
    mock_app = MagicMock()
    mock_app.bot = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    bot._app = mock_app
    bot._is_running = True
    bot.admin_chat_id = 123456789

    assert bot.is_running is True
    await bot.send_notification("Test active message")
    mock_app.bot.send_message.assert_called_once()

    # 4. Simulate RuntimeError ('HTTPXRequest is not initialized') during shutdown
    mock_app.bot.send_message.side_effect = RuntimeError("This HTTPXRequest is not initialized!")
    # Should not raise exception
    await bot.send_notification("Test shutdown message")


@pytest.mark.asyncio
async def test_run_with_restart_clean_shutdown_behavior():
    """Verify that _run_with_restart stops cleanly when component is intentionally stopped or shutdown_event is set."""
    from main import _run_with_restart

    shutdown_event = asyncio.Event()

    class MockComponent:
        def __init__(self):
            self._running = True
            self.call_count = 0

        async def run_loop(self):
            self.call_count += 1
            # Simulate stopping cleanly
            self._running = False
            return None

    comp = MockComponent()
    
    # Run in restart wrapper
    await _run_with_restart("MockComponent", comp.run_loop, shutdown_event, max_restarts=3, base_delay=0.01)
    
    # Should have executed once and stopped cleanly without looping restarts
    assert comp.call_count == 1
