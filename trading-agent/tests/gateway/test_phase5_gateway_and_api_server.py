# ==============================================================================
# File: tests/gateway/test_phase5_gateway_and_api_server.py
# ==============================================================================

"""
Unit Test Suite for Phase 5:
Unified Omnichannel Messaging Gateway, Platform Adapters, and
OpenAI-Compatible Chat Completions API Server (/v1/chat/completions).
"""

import asyncio
import json
import tempfile
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

from database.session_db_wal import SessionDbWal
from gateway.channel_router import ChannelRouter
from gateway.platforms.webhook_adapter import WebhookPlatformAdapter
from gateway.platforms.discord_adapter import DiscordPlatformAdapter
from gateway.platforms.telegram_adapter import TelegramPlatformAdapter
from gateway.api_server import app as api_server_app


# ==============================================================================
# 1. Omnichannel Gateway & ChannelRouter Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_channel_router_multi_platform_routing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_gateway.sqlite"
        db = SessionDbWal(db_path)
        router = ChannelRouter(db)

        webhook_adapter = WebhookPlatformAdapter()
        discord_adapter = DiscordPlatformAdapter()
        telegram_adapter = TelegramPlatformAdapter()

        router.register_adapter(webhook_adapter)
        router.register_adapter(discord_adapter)
        router.register_adapter(telegram_adapter)

        await webhook_adapter.start()
        await discord_adapter.start()
        await telegram_adapter.start()

        # Custom agent pipeline handler
        async def custom_pipeline(session_id: str, user_text: str, metadata: dict) -> str:
            return f"Processed query '{user_text}' for session '{session_id}'"

        router.set_pipeline(custom_pipeline)

        # 1. Webhook incoming
        reply1 = await webhook_adapter.inject_incoming_webhook(
            sender_id="trader_webhook_1",
            channel_id="hook_ch_99",
            text="Buy Signal Alert XAUUSD",
        )
        assert "Processed query 'Buy Signal Alert XAUUSD'" in reply1
        assert "sess_webhook_hook_ch_99" in reply1
        assert len(webhook_adapter.sent_messages) == 1

        # 2. Discord incoming
        reply2 = await discord_adapter.simulate_incoming(
            user_id="discord_user_42",
            channel_id="disc_ch_general",
            message="What is the current EURUSD regime?",
        )
        assert "Processed query 'What is the current EURUSD regime?'" in reply2
        assert "sess_discord_disc_ch_general" in reply2
        assert len(discord_adapter.sent_messages) == 1

        # 3. Verify SessionDbWal persistence
        sess1_msgs = db.get_messages("sess_webhook_hook_ch_99")
        assert len(sess1_msgs) == 2
        assert sess1_msgs[0]["role"] == "user"
        assert sess1_msgs[1]["role"] == "assistant"

        await webhook_adapter.stop()
        await discord_adapter.stop()
        await telegram_adapter.stop()
        db.close()


# ==============================================================================
# 2. OpenAI-Compatible API Server Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_server_health_and_models():
    transport = ASGITransport(app=api_server_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test /health
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        health_data = res_health.json()
        assert health_data["status"] == "healthy"
        assert health_data["two_plane_fortress"] == "active"

        # Test /v1/models
        res_models = await client.get("/v1/models")
        assert res_models.status_code == 200
        models_data = res_models.json()
        assert models_data["object"] == "list"
        model_ids = {m["id"] for m in models_data["data"]}
        assert "monika-trader" in model_ids
        assert "claude-sonnet-5" in model_ids
        assert "gemini-3.8-flash" in model_ids


@pytest.mark.asyncio
async def test_api_server_chat_completions_non_streaming():
    transport = ASGITransport(app=api_server_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_body = {
            "model": "monika-trader",
            "messages": [
                {"role": "system", "content": "You are Monika AI trading system."},
                {"role": "user", "content": "Analyze USDJPY liquidity levels."},
            ],
            "stream": False,
        }
        res = await client.post("/v1/chat/completions", json=req_body)
        assert res.status_code == 200
        data = res.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "monika-trader"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "Monika Trading Intelligence" in data["choices"][0]["message"]["content"]
        assert "usage" in data


@pytest.mark.asyncio
async def test_api_server_chat_completions_streaming():
    transport = ASGITransport(app=api_server_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_body = {
            "model": "monika-trader",
            "messages": [
                {"role": "user", "content": "Stream market overview."},
            ],
            "stream": True,
        }
        res = await client.post("/v1/chat/completions", json=req_body)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

        text_content = res.text
        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
        assert any(l.startswith("data: {") for l in lines)
        assert "data: [DONE]" in lines
