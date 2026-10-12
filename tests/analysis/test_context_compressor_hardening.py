"""
Unit tests for context_compressor hardening (deduplication & anti-thrashing circuit breaker).
"""

import pytest
import time
from analysis.harness.context_compressor import ContextCompressor


def test_tool_result_deduplication():
    compressor = ContextCompressor()

    identical_content = "XAUUSD H1 OHLC: open=2650.0 high=2665.0 low=2648.0 close=2662.0 volume=12500 atr=12.5"
    messages = [
        {"role": "user", "content": "Fetch market data"},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": identical_content},
            ],
        },
        {"role": "assistant", "content": "I will re-read quote"},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_2", "content": identical_content},
            ],
        },
    ]

    pruned = compressor.prune_deterministic_tools(messages)

    # First tool call should be stubbed as duplicate; second (newest) remains intact
    call1_content = pruned[1]["content"][0]["content"]
    call2_content = pruned[3]["content"][0]["content"]

    assert "Duplicate tool observation" in call1_content
    assert call2_content == identical_content


@pytest.mark.asyncio
async def test_anti_thrashing_circuit_breaker():
    compressor = ContextCompressor(settings={"compaction_cooldown_seconds": 60})

    # Message that won't compress much (no middle)
    short_messages = [
        {"role": "system", "content": "A" * 500},
        {"role": "assistant", "content": "B" * 500},
    ]

    # Force 2 ineffective calls
    await compressor.compress(short_messages, max_context_chars=100)
    assert compressor._ineffective_compression_count == 1
    assert compressor._locked_until == 0.0

    await compressor.compress(short_messages, max_context_chars=100)
    assert compressor._ineffective_compression_count == 2
    assert compressor._locked_until > time.time()

    # 3rd call should hit circuit breaker lockout immediately
    result = await compressor.compress(short_messages, max_context_chars=100)
    assert result == short_messages
