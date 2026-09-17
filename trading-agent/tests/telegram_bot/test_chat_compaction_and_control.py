"""
Unit tests for Chat Compaction (H1), Denial Circuit Breaker (M3), and Turn Interruption (M6).
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram_bot.chat_compaction import ChatMicroCompactor
from telegram_bot.chat_agent import ChatAgent


def test_h1_chat_compactor_preserves_user_messages():
    """H1: User messages must never be dropped or truncated by micro compactor."""
    compactor = ChatMicroCompactor(max_history_tokens=100)

    messages = [
        {"role": "user", "content": "What is the price of EURUSD?"},
        {"role": "assistant", "content": "EURUSD is at 1.0850. " + "Detailed technical analysis... " * 50},
        {"role": "user", "content": "Please explain the RSI setup."},
        {"role": "assistant", "content": "RSI is currently oversold at 28.5. " + "Further breakdown... " * 50},
        {"role": "user", "content": "Should I enter now?"},
        {"role": "assistant", "content": "Yes, enter with tight SL at 1.0820."},
    ]

    compacted = compactor.compact_history(messages)

    # All user messages must be preserved verbatim
    user_msgs = [m for m in compacted if m["role"] == "user"]
    assert len(user_msgs) == 3
    assert user_msgs[0]["content"] == "What is the price of EURUSD?"
    assert user_msgs[1]["content"] == "Please explain the RSI setup."
    assert user_msgs[2]["content"] == "Should I enter now?"


def test_m3_denial_circuit_breaker():
    """M3: 3 consecutive proposal denials trigger circuit breaker; resume_proposals resets it."""
    agent = ChatAgent(user_id=12345, settings={})
    assert agent.is_proposals_paused() is False

    # First denial
    paused, msg = agent.record_denial()
    assert paused is False
    assert agent.is_proposals_paused() is False

    # Second denial
    paused, msg = agent.record_denial()
    assert paused is False
    assert agent.is_proposals_paused() is False

    # Third denial triggers circuit breaker
    paused, msg = agent.record_denial()
    assert paused is True
    assert agent.is_proposals_paused() is True
    assert "circuit breaker triggered" in msg.lower() or "paused" in msg.lower()

    # Further proposals remain paused
    paused, msg = agent.record_denial()
    assert paused is True

    # User explicitly resumes proposals
    resumed_msg = agent.resume_proposals()
    assert agent.is_proposals_paused() is False
    assert "resumed" in resumed_msg.lower()


@pytest.mark.asyncio
async def test_m6_turn_interruption():
    """M6: interrupt() cancels active agent generation task cleanly."""
    agent = ChatAgent(user_id=12345, settings={})
    assert agent.is_busy() is False

    # Simulate long running task
    async def long_running_task():
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            return "cancelled"

    task = asyncio.create_task(long_running_task())
    agent._active_task = task
    assert agent.is_busy() is True


    interrupted = agent.interrupt()
    assert interrupted is True
    assert agent.is_busy() is False

    # Calling interrupt again when not busy returns False
    assert agent.interrupt() is False

