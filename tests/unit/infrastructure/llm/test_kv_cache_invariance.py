# ==============================================================================
# File: tests/unit/infrastructure/llm/test_kv_cache_invariance.py
# Description: Unit tests verifying KV Prompt Cache Invariance, Prefix Stability,
#              Breakpoint Budgets, and CacheWarmer Economics (Phase 1 & Phase 2).
# ==============================================================================

import copy
import pytest
from unittest.mock import MagicMock

from monika.infrastructure.llm.context_compaction import ContextCompactionEngine
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager
from monika.infrastructure.llm.cache_warmer import (
    CacheWarmer,
    get_cache_warming_delay_ms,
    get_refresh_deadline_at_ms,
    is_replayable,
    evaluate_warming_decision,
)
from monika.infrastructure.providers.gemini_provider import GeminiProvider
from monika.application.analysis.prompt.prompt_assembler import PromptAssembler, _split_memory


# 1. ContextCompactionEngine.check_and_compact does NOT mutate messages at 15,000 tokens when context_window=128000
def test_compaction_no_mutation_below_high_watermark():
    engine = ContextCompactionEngine()
    # Build messages totaling ~15,000 tokens
    # ~4 chars per token, so ~60,000 chars of tool content
    large_tool_content = "EURUSD M15 candle trend analysis data payload. " * 1200
    messages = [
        {"role": "system", "content": "You are a quantitative trading assistant."},
        {"role": "user", "content": "Analyze EURUSD and check order blocks."},
        {
            "role": "assistant",
            "content": "Fetching price history...",
            "tool_calls": [{"id": "call_1", "function": {"name": "get_price_history", "arguments": "{}"}}],
        },
        {"role": "tool", "name": "get_price_history", "tool_call_id": "call_1", "content": large_tool_content},
        {
            "role": "assistant",
            "content": "Now analyzing liquidity pools.",
            "tool_calls": [{"id": "call_2", "function": {"name": "get_liquidity", "arguments": "{}"}}],
        },
        {"role": "tool", "name": "get_liquidity", "tool_call_id": "call_2", "content": "Liquidity pool at 1.0850"},
    ]

    tokens = engine.calculate_history_tokens(messages)
    assert 10000 < tokens < 30000, f"Expected tokens around 15,000, got {tokens}"

    original_messages = copy.deepcopy(messages)
    compacted = engine.check_and_compact(messages, context_window=128000)

    # Must be 100% byte-identical: zero in-place mutation below high-water mark (80% of 128,000 = 102,400)
    assert len(compacted) == len(original_messages)
    for orig, comp in zip(original_messages, compacted):
        assert orig == comp
    assert compacted[3]["content"] == large_tool_content


# 2. calculate_history_tokens accurately counts Anthropic tool_result ("content"), tool_use, and OpenAI tool_calls
def test_calculate_history_tokens_token_blindness_fixed():
    engine = ContextCompactionEngine()

    # Anthropic style message list with tool_use and tool_result
    anthropic_messages = [
        {
            "role": "user",
            "content": "Check market state",
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Calling market tool"},
                {"type": "tool_use", "id": "toolu_123", "name": "get_market_state", "input": {"symbol": "EURUSD"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_123",
                    "content": "Detailed market state: trend bullish, ATR 14 is 0.0045, high volatility detected.",
                }
            ],
        },
    ]

    anthropic_tokens = engine.calculate_history_tokens(anthropic_messages)
    assert anthropic_tokens > 20, f"Anthropic tokens must be > 20, got {anthropic_tokens}"

    # OpenAI style message with tool_calls and role=tool
    openai_messages = [
        {"role": "user", "content": "Check market state"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "get_market_state", "arguments": '{"symbol": "EURUSD"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_abc",
            "content": "Detailed market state: trend bullish, ATR 14 is 0.0045",
        },
    ]

    openai_tokens = engine.calculate_history_tokens(openai_messages)
    assert openai_tokens > 20, f"OpenAI tokens must be > 20, got {openai_tokens}"

    # Verify last_usage_tokens + delta
    last_tokens = 500
    with_delta = engine.calculate_history_tokens(openai_messages, last_usage_tokens=last_tokens, trailing_delta_count=1)
    assert with_delta > last_tokens


# 3. CacheBreakpointManager never emits >4 cache_control breakpoints and supports ttl="1h"
def test_cache_breakpoint_manager_budget_and_ttl():
    cbm = CacheBreakpointManager()

    # Wrap system tiers with ttl="1h"
    sys_blocks = cbm.wrap_system_tiers(
        tier1_immutable="Identity: Monika quantitative trading assistant.",
        tier2_session_stable="Tools: read, trade, analyze.",
        tier3_cycle_stable="Lessons: respect stop loss and risk limits.",
        ttl="1h",
    )
    assert len(sys_blocks) == 2
    # Verify ttl="1h" is passed
    assert sys_blocks[1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    # Count system breakpoints (<= 2)
    sys_bp_count = sum(1 for b in sys_blocks if isinstance(b, dict) and "cache_control" in b)
    assert sys_bp_count <= 2

    # Messages with multiple completed tool transaction endpoints
    messages = [
        {"role": "user", "content": "Query 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "res1"}]},
        {"role": "assistant", "content": "Response 2"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "res2"}]},
        {"role": "assistant", "content": "Response 3"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t3", "content": "res3"}]},
    ]

    # Apply to messages with default max_message_breakpoints=1 and ttl="1h"
    cached_msgs = cbm.apply_to_messages(messages, ttl="1h")
    msg_bp_count = 0
    for m in cached_msgs:
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and "cache_control" in b:
                    msg_bp_count += 1
                    assert b["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    assert msg_bp_count <= 1
    # Total breakpoints across system (<=2) + tools (1) + messages (<=1) must be <= 4
    tool_bp_count = 1
    total_bp = sys_bp_count + tool_bp_count + msg_bp_count
    assert total_bp <= 4, f"Total breakpoints exceeded Anthropic limit: {total_bp} > 4"


# 4. CacheWarmer delay math, expected savings threshold (>= $0.05), and is_replayable check
def test_cache_warmer_economics_and_replayable():
    # 5-minute TTL = 300,000ms
    ttl_5m = 300_000.0
    delay_5m = get_cache_warming_delay_ms(ttl_5m)
    # min(300_000 * 0.9 = 270_000, 300_000 - 10_000 = 290_000) -> 270_000ms
    assert delay_5m == 270_000.0

    deadline = get_refresh_deadline_at_ms(delay_5m, ttl_5m, delay_5m)
    assert deadline == delay_5m + (ttl_5m - delay_5m) / 2.0

    # Test is_replayable
    assert is_replayable("claude-3-7-sonnet-20250219", thinking_enabled=True, adaptive_thinking=True) is True
    assert is_replayable("gemini-2.5-flash") is True
    assert is_replayable("deepseek-chat") is True
    assert is_replayable("dummy_local_model") is False

    # Test evaluate_warming_decision:
    # In active phase: continuation_prob = 1.0
    # miss_cost = $0.10, warm_cost = $0.01 -> expected_savings = 1.0 * 0.10 - 0.01 = $0.09 >= $0.05 -> True
    dec_active = evaluate_warming_decision(prompt_tokens=20000, warm_cost=0.01, miss_cost=0.10, phase="active")
    assert dec_active["should_warm"] is True
    assert dec_active["expected_savings"] >= 0.05

    # Small miss cost: miss_cost = $0.03, warm_cost = $0.01 -> expected_savings = $0.02 < $0.05 -> False
    dec_small = evaluate_warming_decision(prompt_tokens=20000, warm_cost=0.01, miss_cost=0.03, phase="active")
    assert dec_small["should_warm"] is False

    # Idle phase: continuation_prob = 0.15 -> 0.15 * 0.10 - 0.01 = 0.015 - 0.01 = 0.005 < 0.05 -> False
    dec_idle = evaluate_warming_decision(prompt_tokens=20000, warm_cost=0.01, miss_cost=0.10, phase="idle")
    assert dec_idle["should_warm"] is False


# 5. GeminiProvider._get_api_key stays sticky across calls and only rotates on rotate_api_key()
def test_gemini_provider_sticky_api_key_and_rotation():
    provider = GeminiProvider(
        model="gemini-2.5-flash",
        settings={
            "llm": {
                "providers": {
                    "gemini": {
                        "api_keys": ["KEY_ALPHA", "KEY_BETA", "KEY_GAMMA"],
                        "paid_api_key": "",
                    }
                }
            }
        },
    )
    # Ensure no cooldowns
    GeminiProvider._key_cooldowns.clear()
    GeminiProvider._key_index = 0
    provider.free_api_keys = ["KEY_ALPHA", "KEY_BETA", "KEY_GAMMA"]
    provider.api_key = ""
    provider.paid_api_key = ""

    # Call _get_api_key(sticky=True) 5 times consecutively — must stay sticky on the exact same key!
    k1 = provider._get_api_key(sticky=True)
    k2 = provider._get_api_key(sticky=True)
    k3 = provider._get_api_key(sticky=True)
    k4 = provider._get_api_key(sticky=True)
    k5 = provider._get_api_key(sticky=True)

    assert k1 == "KEY_ALPHA"
    assert k2 == "KEY_ALPHA"
    assert k3 == "KEY_ALPHA"
    assert k4 == "KEY_ALPHA"
    assert k5 == "KEY_ALPHA"

    # Only when rotate_api_key is explicitly called does it advance to the next key
    provider.rotate_api_key()
    k_next = provider._get_api_key(sticky=True)
    assert k_next == "KEY_BETA"


# 6. PromptAssembler.assemble_stage2_tiers strips PORTFOLIO_HEAT: from Tier 3 and includes UNIVERSAL_EXECUTION_DISCIPLINE when inject_anchor=True
def test_prompt_assembler_tier3_memory_split_and_discipline():
    assembler = PromptAssembler(settings={})

    # Test _split_memory with volatile prefixes
    raw_memory = (
        "CORE_RULE: Always wait for 15M confirmation.\n"
        "PORTFOLIO_HEAT: 3.2% exposure\n"
        "HEAT: high\n"
        "UPDATED_AT: 2026-10-21 04:00:00\n"
        "TIMESTAMP: 1729483200\n"
        "UNREALIZED_PNL: +$450.20\n"
        "REGIME_NOW: TRENDING_BULLISH\n"
        "BIAS: Bullish continuation on EURUSD"
    )

    stable, volatile = _split_memory(raw_memory)
    assert "CORE_RULE" in stable
    assert "BIAS" in stable
    assert "PORTFOLIO_HEAT:" not in stable
    assert "HEAT:" not in stable
    assert "UPDATED_AT:" not in stable
    assert "TIMESTAMP:" not in stable
    assert "UNREALIZED_PNL:" not in stable
    assert "REGIME_NOW:" not in stable

    assert "PORTFOLIO_HEAT: 3.2% exposure" in volatile
    assert "UNREALIZED_PNL: +$450.20" in volatile

    # Test assemble_stage2_tiers: volatile heat must not leak into Tier 3
    tier1, tier2, tier3 = assembler.assemble_stage2_tiers(
        symbol="EURUSD",
        cot_code="099741",
        effective_threshold=7,
        min_rr_ratio=1.3,
        core_memory=raw_memory,
        inject_anchor=True,
    )

    assert "PORTFOLIO_HEAT:" not in tier3
    assert "UNREALIZED_PNL:" not in tier3
    assert "CORE_RULE" in tier3

    # When inject_anchor=True, universal discipline must still be present in tier1
    tier1_lower = tier1.lower()
    assert "parallel_tool_dispatch" in tier1_lower or "parallel" in tier1_lower
    assert "literal_preservation" in tier1_lower or "anti_laziness" in tier1_lower or "discipline" in tier1_lower
