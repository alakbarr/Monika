# ==============================================================================
# File: tests/gateway/test_omnichannel_streamer.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from monika.interfaces.gateway.omnichannel_streamer import (
    OmnichannelStreamer,
    scrub_thinking_tokens,
    balance_code_fences,
)
from monika.interfaces.gateway.turn_lease import TurnLeaseManager


def test_scrub_thinking_tokens():
    raw = "<think>Analyzing market context...</think>XAUUSD is currently bullish."
    cleaned, thoughts = scrub_thinking_tokens(raw)
    assert cleaned == "XAUUSD is currently bullish."
    assert "Analyzing market context..." in thoughts


def test_balance_code_fences():
    text_with_open = "Here is Python code:\n```python\nprint('hello')"
    balanced = balance_code_fences(text_with_open)
    assert balanced.endswith("\n```")

    text_already_closed = "Here is Python code:\n```python\nprint('hello')\n```"
    assert balance_code_fences(text_already_closed) == text_already_closed


@pytest.mark.asyncio
async def test_omnichannel_streamer_basic_flow():
    sent_bubbles = []

    async def mock_send(txt: str):
        msg = MagicMock()
        msg.text = txt
        msg.edit_text = AsyncMock()
        sent_bubbles.append(msg)
        return msg

    streamer = OmnichannelStreamer(
        send_message_fn=mock_send,
        initial_interval=0.05,
        max_chars_per_message=200,
    )

    tokens = ["Hello ", "world, ", "this ", "is ", "streaming."]
    for t in tokens:
        await streamer.feed_token(t)

    result = await streamer.finish()
    assert result == "Hello world, this is streaming."
    assert len(sent_bubbles) >= 1


@pytest.mark.asyncio
async def test_omnichannel_streamer_mid_stream_split():
    sent_bubbles = []

    async def mock_send(txt: str):
        msg = MagicMock()
        msg.text = txt
        msg.edit_text = AsyncMock()
        sent_bubbles.append(msg)
        return msg

    streamer = OmnichannelStreamer(
        send_message_fn=mock_send,
        initial_interval=10.0,  # avoid intermediate progressive edits
        max_chars_per_message=50,
    )

    long_payload = "A" * 120
    for ch in long_payload:
        await streamer.feed_token(ch)

    await streamer.finish()
    # 120 chars with limit 50 should produce at least 2 message bubbles
    assert len(sent_bubbles) >= 2


@pytest.mark.asyncio
async def test_omnichannel_streamer_3_strikes_flood_control():
    edit_mock = AsyncMock(side_effect=Exception("429 Too Many Requests: retry after 2"))

    async def mock_send(txt: str):
        msg = MagicMock()
        msg.edit_text = edit_mock
        return msg

    streamer = OmnichannelStreamer(
        send_message_fn=mock_send,
        initial_interval=0.01,
        max_interval=0.04,
        flood_threshold=3,
    )

    for i in range(10):
        await streamer.feed_token(f"Token_{i} ")
        await asyncio.sleep(0.015)

    assert streamer.is_fallback_tail_only is True


@pytest.mark.asyncio
async def test_turn_lease_wait_timeout():
    mgr = TurnLeaseManager(default_ttl=5.0)

    # Holder 1 acquires lease
    acq1 = await mgr.acquire_lease("conv_1", "holder_1", ttl_seconds=1.0)
    assert acq1 is True

    # Holder 2 tries to acquire with short wait_timeout while holder_1 still holds it
    acq2 = await mgr.acquire_lease("conv_1", "holder_2", wait_timeout=0.05)
    assert acq2 is False

    # Now holder 1 releases lease
    await mgr.release_lease("conv_1", "holder_1")

    # Holder 2 should now acquire immediately
    acq3 = await mgr.acquire_lease("conv_1", "holder_2", wait_timeout=0.1)
    assert acq3 is True
