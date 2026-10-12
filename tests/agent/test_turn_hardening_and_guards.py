# ==============================================================================
# File: tests/agent/test_turn_hardening_and_guards.py
# ==============================================================================

import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, patch

from agent.repetition_guard import (
    is_runaway_repetition,
    is_repetition_dominated,
    sanitize_repetition_in_transcript,
    REPETITION_LOOP_INTERRUPTED,
)
from agent.empty_response_guard import (
    EmptyResponseGuard,
    MAX_CONSECUTIVE_EMPTY_FOR_FAILOVER,
)
from agent.scratchpad_guard import (
    has_incomplete_scratchpad,
    extract_reasoning_and_content,
    close_dangling_scratchpad,
)
from agent.estop import (
    arm_estop,
    disarm_estop,
    is_estop_active,
    check_estop_or_raise,
    ESTOPActiveError,
    get_estop_details,
)
from agent.turn_preflight_gate import (
    WallClockBudgetManager,
    TurnPreflightGate,
    RUN_BUDGET_WRAPUP_NOTICE,
)
from agent.turn_tool_round import (
    TurnToolRoundCoordinator,
    ToolCallSpec,
)
from provider.credential_pool import (
    CredentialPool,
    CredentialStatus,
    KeyHealth,
)
from utils.llm.prompt_caching import PromptCacheManager
from analysis.providers.capabilities import get_model_capabilities


# ==============================================================================
# 1. Repetition Guard Tests
# ==============================================================================

def test_repetition_guard_normal_text():
    normal_text = "The market is currently trending upwards due to strong US labor data. EURUSD is holding above 1.0850."
    assert not is_repetition_dominated(normal_text)
    assert not is_runaway_repetition(normal_text)


def test_repetition_guard_runaway_loop():
    repeated_phrase = "Buy EURUSD at 1.0850 with tight stop loss at 1.0820 and take profit at 1.0920. "
    # Repeat until it's over 400 characters and dominated
    runaway_text = repeated_phrase * 8
    assert is_repetition_dominated(runaway_text)
    assert is_runaway_repetition(runaway_text)


def test_repetition_guard_tabular_sql_discrimination():
    # 30 lines of SQL insert with varied values
    sql_lines = [f"INSERT INTO market_quotes VALUES ('EURUSD', {1.0800 + i * 0.001:.4f}, '{time.time() + i}');" for i in range(30)]
    sql_text = "\n".join(sql_lines)
    # Even if long, distinct line ratio is high so it should NOT be flagged as runaway repetition
    assert not is_runaway_repetition(sql_text)


def test_repetition_guard_transcript_immunization():
    repeated_phrase = "Repeating analysis loop text over and over again without stopping now. " * 8
    messages = [
        {"role": "user", "content": "What is EURUSD doing?"},
        {"role": "assistant", "content": repeated_phrase},
    ]
    immunized = sanitize_repetition_in_transcript(messages, repeated_phrase)
    assert immunized[-1]["content"] == REPETITION_LOOP_INTERRUPTED


# ==============================================================================
# 2. Empty Response Guard Tests
# ==============================================================================

def test_empty_response_guard_consecutive_tracking():
    guard = EmptyResponseGuard(cost_threshold_usd=0.25)
    
    # 1st empty response: eligible for retry
    count1 = guard.record_empty_response("openai", "gpt-4o", "stop")
    assert count1 == 1
    can_retry, reason = guard.evaluate_retry_eligibility("openai", "gpt-4o", "stop", current_attempt=0, max_configured_retries=3)
    assert can_retry is True

    # 2nd consecutive empty: failover immediately
    count2 = guard.record_empty_response("openai", "gpt-4o", "stop")
    assert count2 == 2
    can_retry, reason = guard.evaluate_retry_eligibility("openai", "gpt-4o", "stop", current_attempt=1, max_configured_retries=3)
    assert can_retry is False
    assert "Deterministic empty response limit reached" in reason


def test_empty_response_guard_cost_clamping():
    guard = EmptyResponseGuard(cost_threshold_usd=0.20)
    
    # Low cost prompt: allows 3 retries
    can_retry, _ = guard.evaluate_retry_eligibility("anthropic", "claude-3-5-sonnet", "stop", current_attempt=0, max_configured_retries=3, estimated_input_cost_usd=0.05)
    assert can_retry is True

    # High cost prompt: clamped to 1 retry
    can_retry, reason = guard.evaluate_retry_eligibility("anthropic", "claude-3-5-sonnet", "stop", current_attempt=1, max_configured_retries=3, estimated_input_cost_usd=0.50)
    assert can_retry is False
    assert "Retry attempts exhausted" in reason


# ==============================================================================
# 3. Scratchpad Guard Tests
# ==============================================================================

def test_scratchpad_guard_incomplete_tag():
    truncated = "Let me think about this trade setup.\n<think>\nLooking at H4 liquidity pool around 1.0850..."
    assert has_incomplete_scratchpad(truncated) is True

    closed = "Let me think.\n<think>\nAll liquidity swept.\n</think>\nSell EURUSD now."
    assert has_incomplete_scratchpad(closed) is False


def test_scratchpad_guard_extraction():
    content = "Initiating analysis.\n<think>\nSMC Orderblock active.\n</think>\nTrade signal: BUY."
    reasoning, visible, is_inc = extract_reasoning_and_content(content)
    assert reasoning == "SMC Orderblock active."
    assert "Trade signal: BUY." in visible
    assert "<think>" not in visible
    assert is_inc is False


def test_scratchpad_guard_close_dangling():
    dangling = "<think>\nThinking about rate cuts..."
    fixed = close_dangling_scratchpad(dangling)
    assert "</think>" in fixed
    assert not has_incomplete_scratchpad(fixed)


# ==============================================================================
# 4. ESTOP Sentinel Tests
# ==============================================================================

def test_estop_lifecycle():
    # Clean state before test
    disarm_estop()
    assert not is_estop_active()

    # Arm ESTOP
    path = arm_estop(reason="Flash crash test", actor="unit_test")
    assert is_estop_active()
    assert path.exists()

    details = get_estop_details()
    assert details is not None
    assert details.get("reason") == "Flash crash test"
    assert details.get("actor") == "unit_test"

    with pytest.raises(ESTOPActiveError):
        check_estop_or_raise("Order Execution")

    # Disarm ESTOP
    assert disarm_estop() is True
    assert not is_estop_active()


# ==============================================================================
# 5. Turn Preflight Gate Tests
# ==============================================================================

def test_preflight_context_floor():
    ok, _ = TurnPreflightGate.validate_context_floor(context_window=128000, estimated_required_tokens=4096)
    assert ok is True

    fail, msg = TurnPreflightGate.validate_context_floor(context_window=2048, estimated_required_tokens=4096)
    assert fail is False
    assert "Context floor violation" in msg


def test_preflight_compression_progress():
    # Meaningful 50% reduction
    assert TurnPreflightGate.compression_warrants_another_pass(10000, 5000, min_reduction_ratio=0.05) is True

    # Negligible 1% reduction -> blocked
    assert TurnPreflightGate.compression_warrants_another_pass(10000, 9950, min_reduction_ratio=0.05) is False


def test_wall_clock_budget_wrapup():
    budget = WallClockBudgetManager(budget_seconds=1.0, wrapup_ratio=0.80)
    assert not budget.should_inject_wrapup()
    
    # Simulate time lapse by shifting start_time
    budget.start_time = time.time() - 0.85
    assert budget.should_inject_wrapup() is True
    
    notice = budget.get_wrapup_notice()
    assert RUN_BUDGET_WRAPUP_NOTICE == notice
    
    budget.mark_wrapup_injected()
    assert not budget.should_inject_wrapup()


# ==============================================================================
# 6. Turn Tool Round & Persist-Before-Execute Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_turn_tool_round_persist_before_execute_failure():
    # If persistence fails, coordinator fails closed and tool executor is NEVER called
    mock_persist = AsyncMock(return_value=False)
    mock_executor = AsyncMock()

    coordinator = TurnToolRoundCoordinator(persist_callback=mock_persist)
    raw_calls = [{"id": "c1", "function": {"name": "place_order", "arguments": '{"symbol": "EURUSD"}'}}]

    verdict = await coordinator.execute_tool_round(raw_calls, mock_executor)
    
    assert verdict.action == "break"
    assert verdict.persistence_failed is True
    # The crucial invariant: tool was NEVER executed!
    mock_executor.assert_not_called()


@pytest.mark.asyncio
async def test_turn_tool_round_persist_before_execute_success():
    mock_persist = AsyncMock(return_value=True)
    mock_executor = AsyncMock(return_value={"status": "order_placed"})

    coordinator = TurnToolRoundCoordinator(persist_callback=mock_persist)
    raw_calls = [{"id": "c1", "function": {"name": "place_order", "arguments": '{"symbol": "EURUSD"}'}}]

    verdict = await coordinator.execute_tool_round(raw_calls, mock_executor)
    
    assert verdict.action == "continue"
    assert verdict.persistence_failed is False
    assert len(verdict.tool_results) == 1
    assert "order_placed" in verdict.tool_results[0]["content"]
    mock_executor.assert_called_once_with("place_order", {"symbol": "EURUSD"})


@pytest.mark.asyncio
async def test_turn_tool_round_estop_halts():
    arm_estop("Test Halt", actor="pytest")
    try:
        mock_persist = AsyncMock(return_value=True)
        mock_executor = AsyncMock()

        coordinator = TurnToolRoundCoordinator(persist_callback=mock_persist)
        raw_calls = [{"id": "c1", "function": {"name": "place_order", "arguments": "{}"}}]

        verdict = await coordinator.execute_tool_round(raw_calls, mock_executor)
        assert verdict.action == "break"
        assert "Emergency Stop" in (verdict.halt_reason or "")
        mock_executor.assert_not_called()
    finally:
        disarm_estop()


# ==============================================================================
# 7. Credential Pool Resilience Enhancements Tests
# ==============================================================================

def test_credential_pool_status_and_sibling_propagation():
    pool = CredentialPool(auto_init_env=False, rotation_strategy="round_robin")
    
    # Register same key under two providers to test sibling propagation
    shared_key = "sk-shared-key-test-12345"
    pool.add_key("openai", shared_key)
    pool.add_key("openrouter", shared_key)

    k1 = pool._pools["openai"][0]
    k2 = pool._pools["openrouter"][0]

    assert k1.status == CredentialStatus.STATUS_OK
    assert k2.status == CredentialStatus.STATUS_OK

    # Report rate limit on openai -> should propagate to openrouter sibling
    pool.report_rate_limit("openai", shared_key, cooldown_seconds=120.0)

    assert k1.status == CredentialStatus.STATUS_EXHAUSTED
    assert k2.status == CredentialStatus.STATUS_EXHAUSTED
    assert k1.is_in_cooldown
    assert k2.is_in_cooldown


def test_credential_pool_rotation_strategies():
    pool = CredentialPool(auto_init_env=False, rotation_strategy="fill_first")
    pool.add_key("testprov", "key_A")
    pool.add_key("testprov", "key_B")

    # fill_first should always pick key_A until key_A is in cooldown
    assert pool.get_key("testprov") == "key_A"
    assert pool.get_key("testprov") == "key_A"

    # Put key_A in cooldown -> should pick key_B
    pool.report_rate_limit("testprov", "key_A", cooldown_seconds=60.0)
    assert pool.get_key("testprov") == "key_B"


# ==============================================================================
# 8. Modern Capabilities & Prompt Caching 4-Breakpoint Tests
# ==============================================================================

def test_capabilities_modern_models():
    # User specified modern models:
    sonnet5 = get_model_capabilities("claude-sonnet-5")
    assert sonnet5.supports_caching is True
    assert sonnet5.max_output_tokens == 32768

    gemini38 = get_model_capabilities("gemini-3.8-flash")
    assert gemini38.supports_caching is True
    assert gemini38.context_window == 2097152

    gpt6 = get_model_capabilities("gpt-6-astra")
    assert gpt6.supports_caching is True
    assert gpt6.context_window == 500000

    deepseek_v4 = get_model_capabilities("deepseek-v4-pro")
    assert deepseek_v4.supports_caching is True
    assert deepseek_v4.max_output_tokens == 32768


def test_prompt_caching_4breakpoint():
    sys_prompt = "You are Monika Trading Agent.\n---\nMarket session: LONDON. Open positions: 2."
    tools = [{"name": "get_quote"}, {"name": "place_order"}]
    messages = [
        {"role": "user", "content": "Analyze GBPUSD."},
        {"role": "assistant", "content": "Checking market structure."},
        {"role": "user", "content": "Also check EURUSD."},
    ]

    # Test main agent cache (1h TTL)
    sys_blocks, cached_tools, cached_msgs = PromptCacheManager.apply_4breakpoint_cache(
        system_prompt=sys_prompt,
        tools=tools,
        messages=messages,
        is_subagent=False,
    )

    assert len(sys_blocks) == 2
    assert sys_blocks[0]["cache_control"]["ttl"] == "1h"
    assert cached_tools[-1]["cache_control"]["ttl"] == "1h"
    # Check that messages received cache control
    assert "cache_control" in cached_msgs[-1]["content"][-1]

    # Test subagent TTL demotion (5m TTL)
    sub_blocks, sub_tools, _ = PromptCacheManager.apply_4breakpoint_cache(
        system_prompt="Short worker prompt",
        tools=tools,
        messages=messages,
        is_subagent=True,
    )
    assert sub_blocks[-1]["cache_control"]["ttl"] == "5m"
    assert sub_tools[-1]["cache_control"]["ttl"] == "5m"
