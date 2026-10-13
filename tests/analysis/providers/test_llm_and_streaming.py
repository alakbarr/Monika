# ==============================================================================
# File: tests/analysis/providers/test_phase6_llm_and_streaming.py
# ==============================================================================

import asyncio
import time
import pytest

from analysis.providers.provider_profile import (
    ProviderProfile,
    NormalizedResponse,
    NormalizedToolCall,
    TokenUsage,
    get_provider_profile,
)
from utils.streaming.streaming_lease import (
    StreamWriterLeaseCoordinator,
    StreamWriterLeaseHandle,
    LeaseAcquisitionTimeoutError,
    LeaseExpiredOrInvalidError,
)
from provider.credential_pool import KeyHealth, CredentialPool


def test_provider_profile_normalize_string_and_think_tags():
    profile = get_provider_profile("deepseek")
    assert profile.supports_native_thinking is True

    raw_text = "<think>Analyzing market liquidity and EURUSD order flow.</think>The current regime is neutral."
    normalized = profile.normalize_response(raw_text, model_name="deepseek-r1")

    assert normalized.reasoning_content == "Analyzing market liquidity and EURUSD order flow."
    assert normalized.text == "The current regime is neutral."
    assert normalized.model == "deepseek-r1"
    assert normalized.provider == "deepseek"
    assert normalized.has_tool_calls is False


def test_provider_profile_normalize_openai_dict():
    profile = get_provider_profile("openai")
    raw_dict = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_market_quote",
                                "arguments": "{\"symbol\": \"EURUSD\"}",
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "prompt_tokens_details": {"cached_tokens": 64},
            "completion_tokens_details": {"reasoning_tokens": 10},
        },
    }

    normalized = profile.normalize_response(raw_dict, model_name="gpt-4o")

    assert normalized.has_tool_calls is True
    assert len(normalized.tool_calls) == 1
    assert normalized.tool_calls[0].name == "get_market_quote"
    assert normalized.tool_calls[0].arguments == {"symbol": "EURUSD"}
    assert normalized.usage.cached_tokens == 64
    assert normalized.usage.reasoning_tokens == 10
    assert normalized.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_stream_writer_lease_single_writer_exclusion():
    coordinator = StreamWriterLeaseCoordinator(default_duration_sec=2.0)
    surface = "telegram:chat:9999"
    chunks_written = []

    async def writer_one():
        async with coordinator.acquire_lease(surface, owner="task_one", timeout_sec=1.0) as lease:
            await lease.write("chunk_1", writer_fn=lambda c: chunks_written.append(c))
            await asyncio.sleep(0.3)
            await lease.write("chunk_2", writer_fn=lambda c: chunks_written.append(c))

    async def writer_two():
        # Will wait until writer_one completes because of exclusive surface lock
        async with coordinator.acquire_lease(surface, owner="task_two", timeout_sec=2.0) as lease:
            await lease.write("chunk_3", writer_fn=lambda c: chunks_written.append(c))

    await asyncio.gather(writer_one(), writer_two())
    assert chunks_written == ["chunk_1", "chunk_2", "chunk_3"]


@pytest.mark.asyncio
async def test_stream_writer_lease_timeout():
    coordinator = StreamWriterLeaseCoordinator(default_duration_sec=5.0)
    surface = "terminal:stdout"

    async with coordinator.acquire_lease(surface, owner="holder", timeout_sec=1.0):
        # Second acquire should timeout because timeout_sec is 0.1s and holder holds lock
        with pytest.raises(LeaseAcquisitionTimeoutError):
            async with coordinator.acquire_lease(surface, owner="contender", timeout_sec=0.1):
                pass


def test_credential_pool_proactive_header_rate_limiting():
    pool = CredentialPool(auto_init_env=False)
    pool.add_key("openai", "sk-proj-test12345678901234567890")

    key_health = pool._pools["openai"][0]
    assert key_health.is_available is True

    # 1. Provide response headers indicating remaining requests = 0, retry-after = 15s
    headers = {
        "x-ratelimit-remaining-requests": "0",
        "retry-after": "15",
    }
    pool.record_response_headers("openai", "sk-proj-test12345678901234567890", headers)

    # Key should now be in cooldown proactively BEFORE any 429 error!
    assert key_health.is_in_cooldown is True
    assert key_health.is_available is False
    assert key_health.cooldown_until > time.time()
