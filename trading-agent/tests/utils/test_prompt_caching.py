# ==============================================================================
# File: tests/utils/test_prompt_caching.py
# ==============================================================================

import pytest
from utils.llm.prompt_caching import PromptCacheManager, PromptCacheTracker


def test_anthropic_cache_breakpoints():
    """Verify ephemeral breakpoints placed on system prompt and last tool."""
    system_prompt = "You are a senior hedge fund analyst."
    tools = [
        {"name": "get_price_data", "description": "Fetch prices"},
        {"name": "get_technical_analysis", "description": "Calculate indicators"},
    ]
    messages = [{"role": "user", "content": "Analyze EURUSD"}]

    sys_blocks, cached_tools, cached_msgs = PromptCacheManager.apply_anthropic_cache(
        system_prompt=system_prompt,
        tools=tools,
        messages=messages
    )

    # Verify system block has ephemeral cache control
    assert len(sys_blocks) == 1
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert sys_blocks[0]["text"] == system_prompt

    # Verify last tool has cache control, but first tool does not
    assert len(cached_tools) == 2
    assert "cache_control" not in cached_tools[0]
    assert cached_tools[1]["cache_control"] == {"type": "ephemeral"}


def test_prompt_partition_3tier():
    """Verify stable prefix is separated from volatile suffix."""
    soul = "Identity: Sovereign Trading Agent."
    guidelines = "Guidelines: Never risk > 1% without verification."
    dynamic = "Market Data: EURUSD 1.0850, Time: 2026-09-06T00:00:00Z"

    prefix, suffix = PromptCacheManager.partition_3tier_prompt(
        identity_soul=soul,
        instructions_guidelines=guidelines,
        dynamic_context=dynamic
    )

    assert "Identity: Sovereign Trading Agent." in prefix
    assert "Never risk > 1%" in prefix
    assert "EURUSD 1.0850" not in prefix
    assert "EURUSD 1.0850" in suffix


def test_cache_tracker_metrics():
    """Verify tracker accurately computes cumulative hit rates."""
    tracker = PromptCacheTracker()
    tracker.record_turn(input_tokens=1000, cached_tokens=500, cache_creation_tokens=1000)
    tracker.record_turn(input_tokens=500, cached_tokens=1500, cache_creation_tokens=0)

    summary = tracker.get_summary()
    assert summary["total_turns"] == 2
    assert summary["total_input_tokens"] == 1500
    assert summary["total_cache_read_tokens"] == 2000
    # Hit rate = 2000 / (1500 + 2000) = 2000 / 3500 ~= 0.5714
    assert 0.57 < summary["cache_hit_rate"] < 0.58
