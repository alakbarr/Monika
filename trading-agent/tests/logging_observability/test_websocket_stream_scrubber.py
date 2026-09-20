import pytest
from unittest.mock import AsyncMock, MagicMock
from logging_observability.dashboard.routes.websocket import TokenCoalescingBuffer
from utils.streaming.stream_scrubber import StatefulStreamScrubber


@pytest.mark.asyncio
async def test_token_coalescing_buffer_scrubs_thinking_blocks():
    mock_ws = AsyncMock()
    sent_deltas = []

    async def mock_send_json(payload):
        if payload.get("type") == "delta":
            sent_deltas.append(payload.get("text"))

    mock_ws.send_json.side_effect = mock_send_json

    buffer = TokenCoalescingBuffer(websocket=mock_ws, flush_interval=0.001, max_buffer_chars=10, scrub=True)

    # Push chunks that include <think> reasoning
    await buffer.push("Visible start. ")
    await buffer.push("<think>Deep private reasoning")
    await buffer.push(" and model analysis</think>")
    await buffer.push("Visible conclusion.")
    await buffer.flush(final=True)

    combined_text = "".join(sent_deltas)
    assert "<think>" not in combined_text
    assert "</think>" not in combined_text
    assert "Deep private reasoning" not in combined_text
    assert "Visible start." in combined_text
    assert "Visible conclusion." in combined_text


@pytest.mark.asyncio
async def test_token_coalescing_buffer_redacts_secrets():
    mock_ws = AsyncMock()
    sent_deltas = []

    async def mock_send_json(payload):
        if payload.get("type") == "delta":
            sent_deltas.append(payload.get("text"))

    mock_ws.send_json.side_effect = mock_send_json

    buffer = TokenCoalescingBuffer(websocket=mock_ws, flush_interval=0.001, max_buffer_chars=5, scrub=True)

    await buffer.push("Connecting with token: ")
    await buffer.push("bot123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12345")
    await buffer.push(" on MT5.")
    await buffer.flush(final=True)

    combined_text = "".join(sent_deltas)
    assert "bot123456789" not in combined_text
    assert "[REDACTED_TELEGRAM_TOKEN]" in combined_text


def test_scrub_text_classmethod():
    raw_input = "Hello! <think>pondering bias</think>Here is the trade setup. api_key='sk-1234567890abcdef1234567890'"
    sanitized = StatefulStreamScrubber.scrub_text(raw_input)

    assert "<think>" not in sanitized
    assert "pondering bias" not in sanitized
    assert "sk-1234567890" not in sanitized
    assert "Here is the trade setup." in sanitized
    assert "[REDACTED_SECRET]" in sanitized or "[REDACTED_API_KEY]" in sanitized
