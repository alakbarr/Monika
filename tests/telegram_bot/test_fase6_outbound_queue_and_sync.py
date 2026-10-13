# ==============================================================================
# File: tests/telegram_bot/test_fase6_outbound_queue_and_sync.py
# Description: Unit tests for Phase 6 (Telegram Outbound Queue, Anti-FloodWait,
#              Offline Disk Buffer, and API Gateway Contract Synchronization)
# ==============================================================================

import asyncio
import os
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from telegram.error import RetryAfter, NetworkError

from monika.interfaces.telegram.bot import TelegramBot
from monika.interfaces.dashboard.api import app, _allowed_origins
from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_telegram_outbound_queue_send_and_rate_limiting(tmp_path):
    """Verify outbound queue worker consumes items with token-bucket rate limiting."""
    bot = TelegramBot(settings={})
    bot.admin_chat_id = 12345
    bot._is_running = True
    bot._offline_queue_file = str(tmp_path / "offline_queue.jsonl")

    mock_send = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot.send_message = mock_send
    bot._app = mock_app

    worker = asyncio.create_task(bot._process_outbound_queue())
    bot._outbound_worker_task = worker

    # Send 2 notifications
    await bot.send_notification("Message 1")
    await bot.send_notification("Message 2")

    await asyncio.sleep(1.2)  # Allow per-chat 1.0s interval to pass

    bot._is_running = False
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError, Exception:
        pass

    assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_telegram_outbound_retry_after_backoff(tmp_path):
    """Verify RetryAfter exception pauses queue and retries successfully."""
    bot = TelegramBot(settings={})
    bot.admin_chat_id = 12345
    bot._is_running = True
    bot._offline_queue_file = str(tmp_path / "offline_queue.jsonl")

    # Raise RetryAfter(0.05) on first call, then succeed
    mock_send = AsyncMock()
    mock_send.side_effect = [RetryAfter(0.05), MagicMock()]

    mock_app = MagicMock()
    mock_app.bot.send_message = mock_send
    bot._app = mock_app

    worker = asyncio.create_task(bot._process_outbound_queue())
    bot._outbound_worker_task = worker

    await bot.send_notification("Alert with flood control")
    for _ in range(20):
        if mock_send.call_count >= 2:
            break
        await asyncio.sleep(0.05)

    bot._is_running = False
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError, Exception:
        pass

    assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_telegram_offline_buffer_persistence_and_flush(tmp_path):
    """Verify critical alerts persist to disk during network error and flush upon reconnection."""
    offline_file = str(tmp_path / "offline_queue.jsonl")
    bot = TelegramBot(settings={})
    bot.admin_chat_id = 12345
    bot._is_running = True
    bot._offline_queue_file = offline_file

    mock_send = AsyncMock(side_effect=NetworkError("Connection refused"))
    mock_app = MagicMock()
    mock_app.bot.send_message = mock_send
    bot._app = mock_app

    worker = asyncio.create_task(bot._process_outbound_queue())
    bot._outbound_worker_task = worker

    # Critical alert that matches keyword "RiskGate"
    await bot.send_notification("🚨 RiskGate Breach: Max Drawdown Exceeded", is_critical=True)
    await asyncio.sleep(0.1)

    bot._is_running = False
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError, Exception:
        pass

    # Verify saved to disk buffer
    assert os.path.exists(offline_file)
    with open(offline_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "RiskGate Breach" in content

    # Now simulate recovery and flush
    bot._is_running = True
    await bot._flush_offline_queue()

    # Outbound queue should now have the recovered item
    assert bot._outbound_queue.qsize() == 1
    recovered_item = await bot._outbound_queue.get()
    assert "RECOVERED OFFLINE ALERT" in recovered_item["text"]
    assert not os.path.exists(offline_file)


def test_action_close_batch_contract_synchronization():
    """Verify POST /api/actions/close-batch aligns contract with frontend expectations."""
    client = TestClient(app, headers={"X-API-Key": "test_adm_key"})
    env = {"DASHBOARD_API_KEYS": "admin:test_adm_key"}

    with patch.dict(os.environ, env):
        with patch("monika.infrastructure.database.db.AsyncSessionLocal") as mock_sess_cls:
            mock_session = create_mock_async_session()
            mock_sess_cls.return_value.__aenter__.return_value = mock_session

            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_res)
            mock_session.commit = AsyncMock()

            resp = client.post(
                "/api/actions/close-batch",
                json={"tickets": [101, 102], "reason": "Test close batch"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "closed_count" in data
            assert "failed_count" in data
            assert "message" in data
            assert "result" in data


def test_dashboard_cors_origins():
    """Verify 127.0.0.1 Vite dev server origins are authorized in CORS."""
    assert "http://127.0.0.1:5173" in _allowed_origins
    assert "http://127.0.0.1:4173" in _allowed_origins
