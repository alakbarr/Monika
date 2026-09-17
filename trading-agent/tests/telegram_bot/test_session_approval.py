# ==============================================================================
# File: tests/telegram_bot/test_session_approval.py
# ==============================================================================

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram_bot.chat_agent import ChatAgent, PendingAction
from telegram_bot.command_router import CommandRouter


def test_command_router_3_tier_buttons():
    kb = CommandRouter.build_confirm_keyboard("act999")
    buttons = kb.inline_keyboard
    assert len(buttons) == 2  # 2 rows

    row1 = buttons[0]
    assert len(row1) == 2
    assert row1[0].text == "✅ Allow Once"
    assert row1[0].callback_data == "confirm:act999"
    assert row1[1].text == "⏳ Allow for Session (4h)"
    assert row1[1].callback_data == "allow_session:act999"

    row2 = buttons[1]
    assert len(row2) == 1
    assert row2[0].text == "❌ Deny"
    assert row2[0].callback_data == "reject:act999"


@pytest.mark.asyncio
async def test_chat_agent_session_approval_grant_and_check():
    agent = ChatAgent(settings={}, user_id=123)

    assert agent.is_symbol_session_approved("XAUUSD") is False

    expiry = agent.add_session_approval("XAUUSD")
    assert agent.is_symbol_session_approved("XAUUSD") is True
    # Case and formatting insensitivity
    assert agent.is_symbol_session_approved("xauusd") is True
    assert agent.is_symbol_session_approved("XAU/USD") is True
    assert agent.is_symbol_session_approved("EURUSD") is False

    # Check expiry time is roughly 4 hours ahead
    delta = expiry - datetime.now(timezone.utc)
    assert 3.9 <= (delta.total_seconds() / 3600.0) <= 4.1


@pytest.mark.asyncio
async def test_chat_agent_session_approval_expiry():
    agent = ChatAgent(settings={}, user_id=123)
    # Set expired approval in the past
    agent._session_approvals["EURUSD"] = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert agent.is_symbol_session_approved("EURUSD") is False
    assert "EURUSD" not in agent._session_approvals


@pytest.mark.asyncio
@patch("telegram_bot.chat_agent.get_session")
async def test_chat_agent_approve_for_session(mock_get_session):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_get_session.return_value = mock_ctx

    agent = ChatAgent(settings={}, user_id=123)
    action = PendingAction(
        action_id="act_test_1",
        action_type="place_order",
        params={"symbol": "GBPUSD", "direction": "buy", "lots": 0.1},
        description="Buy 0.1 lots GBPUSD",
    )
    agent._pending_actions["act_test_1"] = action

    agent._execute_action = AsyncMock(return_value="Order Placed ticket=55555")

    success, msg = await agent.approve_for_session("act_test_1")
    assert success is True
    assert "Order Placed" in msg
    assert "Izin Sesi Aktif" in msg
    assert "GBPUSD" in msg
    assert agent.is_symbol_session_approved("GBPUSD") is True


@pytest.mark.asyncio
@patch("telegram_bot.chat_agent.get_client_for_task")
@patch("telegram_bot.chat_agent.get_session")
async def test_chat_agent_auto_execute_when_session_approved(mock_get_session, mock_get_client):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_get_session.return_value = mock_ctx

    mock_client = mock_get_client.return_value
    mock_client.model = "gemini-3.1-flash-lite"
    mock_client.model_name = "gemini-3.1-flash-lite"
    mock_client.run_chat_loop = AsyncMock(return_value={
        "reply": "Executing buy setup for BTCUSD.",
        "proposed_action": {
            "action_type": "place_order",
            "params": {"symbol": "BTCUSD", "direction": "buy", "lots": 0.05},
            "description": "Buy 0.05 BTCUSD",
        },
        "input_tokens": 80,
        "output_tokens": 40,
    })

    agent = ChatAgent(settings={}, user_id=123)
    agent.add_session_approval("BTCUSD")

    agent._save_message = AsyncMock()
    agent._load_history = AsyncMock(return_value=[])
    agent._build_system_prompt = AsyncMock(return_value="System prompt")
    agent._execute_action = AsyncMock(return_value="Order Placed ticket=77777")

    reply, pending = await agent.handle("Beli BTC dong")

    # When session is approved, pending should be None (auto-executed)
    assert pending is None
    assert "Auto-Executed (Session Approval Active for BTCUSD)" in reply
    assert "Order Placed ticket=77777" in reply
    agent._execute_action.assert_called_once()
