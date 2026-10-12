# ==============================================================================
# File: tests/analysis/test_streaming.py
# ==============================================================================

"""Unit tests for universal streaming consumer and idle timeout engine."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from utils.api.streaming import (
    consume_sse_stream,
    StreamConfig,
    StreamResult,
    StreamTimeoutError,
    StreamSafetyTimeoutError,
)
from analysis.providers.gemini_provider import _gemini_stream_parser


class MockStreamReader:
    """Mock aiohttp response.content StreamReader."""
    def __init__(self, chunks: list[bytes], delays: list[float] = None):
        self.chunks = list(chunks)
        self.delays = list(delays) if delays else [0.0] * len(chunks)
        self.idx = 0

    async def read(self, n: int = -1) -> bytes:
        if self.idx >= len(self.chunks):
            return b""
        delay = self.delays[self.idx] if self.idx < len(self.delays) else 0.0
        if delay > 0:
            await asyncio.sleep(delay)
        chunk = self.chunks[self.idx]
        self.idx += 1
        return chunk


class MockClientResponse:
    """Mock aiohttp.ClientResponse."""
    def __init__(self, chunks: list[bytes], delays: list[float] = None, status: int = 200):
        self.status = status
        self.content = MockStreamReader(chunks, delays)
        self.headers = {}


@pytest.mark.asyncio
async def test_consume_sse_basic():
    """Test standard SSE stream consumption and text aggregation."""
    sse_data = (
        b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"Hello \"}]}}]}\n\n"
        b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"World!\"}]}, \"finishReason\": \"STOP\"}], \"usageMetadata\": {\"promptTokenCount\": 10, \"candidatesTokenCount\": 5}}\n\n"
    )
    resp = MockClientResponse([sse_data])
    config = StreamConfig(idle_timeout=5.0, safety_timeout=10.0, first_chunk_timeout=5.0)

    result = await consume_sse_stream(resp, config, _gemini_stream_parser, model_name="gemini-3.7-flash")

    assert result.text == "Hello World!"
    assert result.finish_reason == "STOP"
    assert result.usage.get("promptTokenCount") == 10
    assert result.usage.get("candidatesTokenCount") == 5
    assert result.chunks_received == 2


@pytest.mark.asyncio
async def test_consume_sse_done_marker():
    """Test standard OpenAI/Groq [DONE] marker."""
    def openai_dummy_parser(chunk: dict, res: StreamResult) -> bool:
        for c in chunk.get("choices", []):
            delta = c.get("delta", {})
            if "content" in delta:
                res.text += delta["content"]
        return False

    sse_data = (
        b"data: {\"choices\": [{\"delta\": {\"content\": \"Signal: \"}}]}\n\n"
        b"data: {\"choices\": [{\"delta\": {\"content\": \"BUY EURUSD\"}}]}\n\n"
        b"data: [DONE]\n\n"
    )
    resp = MockClientResponse([sse_data])
    config = StreamConfig(idle_timeout=5.0, safety_timeout=10.0, first_chunk_timeout=5.0)

    result = await consume_sse_stream(resp, config, openai_dummy_parser, model_name="gpt-4o")

    assert result.text == "Signal: BUY EURUSD"
    assert result.chunks_received == 2


@pytest.mark.asyncio
async def test_consume_sse_idle_timeout():
    """Test that idle timeout raises StreamTimeoutError when chunks stop arriving."""
    chunks = [
        b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"Part 1\"}]}}]}\n\n",
        b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"Part 2\"}]}}]}\n\n",
    ]
    # First chunk instant, second chunk delayed 0.5s with idle timeout 0.1s
    delays = [0.0, 0.5]
    resp = MockClientResponse(chunks, delays)
    config = StreamConfig(idle_timeout=0.1, safety_timeout=5.0, first_chunk_timeout=0.5)

    with pytest.raises(StreamTimeoutError) as exc_info:
        await consume_sse_stream(resp, config, _gemini_stream_parser, model_name="gemini-test")

    assert "idle timeout" in str(exc_info.value)
    assert exc_info.value.chunks_received == 1


@pytest.mark.asyncio
async def test_consume_sse_first_chunk_timeout():
    """Test that first_chunk_timeout raises StreamTimeoutError when model takes too long to start."""
    chunks = [
        b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"First\"}]}}]}\n\n",
    ]
    delays = [0.4]
    resp = MockClientResponse(chunks, delays)
    config = StreamConfig(idle_timeout=1.0, safety_timeout=5.0, first_chunk_timeout=0.1)

    with pytest.raises(StreamTimeoutError) as exc_info:
        await consume_sse_stream(resp, config, _gemini_stream_parser, model_name="gemini-test")

    assert "first chunk timeout" in str(exc_info.value)
    assert exc_info.value.chunks_received == 0


@pytest.mark.asyncio
async def test_consume_sse_comment_keepalive():
    """Test that SSE comment lines (: keepalive) prevent idle timeout."""
    chunks = [
        b": OPENROUTER PROCESSING\n\n",
        b": OPENROUTER PROCESSING\n\n",
        b"data: {\"choices\": [{\"delta\": {\"content\": \"Result arrived!\"}}]}\n\n",
        b"data: [DONE]\n\n",
    ]
    # Each chunk delayed 0.15s, idle_timeout 0.25s
    delays = [0.15, 0.15, 0.15, 0.0]
    resp = MockClientResponse(chunks, delays)
    config = StreamConfig(idle_timeout=0.25, safety_timeout=5.0, first_chunk_timeout=0.25)

    def simple_parser(chunk: dict, res: StreamResult) -> bool:
        for c in chunk.get("choices", []):
            delta = c.get("delta", {})
            if "content" in delta:
                res.text += delta["content"]
        return False

    result = await consume_sse_stream(resp, config, simple_parser, model_name="openrouter-test")
    assert result.text == "Result arrived!"


@pytest.mark.asyncio
async def test_gemini_parser_thinking_and_tool_call():
    """Test Gemini chunk parser handles thought tokens and tool calls properly."""
    result = StreamResult()

    chunk_thought = {
        "candidates": [{
            "content": {
                "parts": [{"thought": True, "text": "Analyzing macro regime..."}],
                "role": "model"
            }
        }]
    }
    _gemini_stream_parser(chunk_thought, result)
    assert result.thinking_text == "Analyzing macro regime..."
    assert result.text == ""

    chunk_tool = {
        "candidates": [{
            "content": {
                "parts": [{
                    "functionCall": {"name": "get_dxy", "args": {}},
                    "thoughtSignature": "sig_12345"
                }],
                "role": "model"
            },
            "finishReason": "STOP"
        }],
        "usageMetadata": {
            "promptTokenCount": 50,
            "candidatesTokenCount": 20
        }
    }
    is_done = _gemini_stream_parser(chunk_tool, result)
    assert is_done is True
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_dxy"
    assert result.tool_calls[0]["thoughtSignature"] == "sig_12345"
    assert result.usage["promptTokenCount"] == 50
