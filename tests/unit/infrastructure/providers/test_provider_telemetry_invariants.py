# ==============================================================================
# File: tests/unit/infrastructure/providers/test_provider_telemetry_invariants.py
# Description: Regression tests for prompt cache hit rate formula, token accounting
# invariants across all provider adapters, and explicit task_role attribution.
# ==============================================================================

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.infrastructure.llm.context_tracker import ContextTracker
from monika.infrastructure.llm.prompt_caching import PromptCacheTracker
from monika.infrastructure.providers.base_provider import BaseLLMClient
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.providers.anthropic_provider import AnthropicProvider
from monika.infrastructure.providers.typesafe_provider import TypeSafeProvider


def test_context_tracker_hit_rate_invariant_no_double_counting():
    """Invariant: input_tokens represents total prompt tokens.
    Hit rate must be cached_tokens / input_tokens without adding cached_tokens again."""
    tracker = ContextTracker(default_model="claude-3-5-sonnet")

    # 5,000 cached out of 10,000 total prompt tokens = 50.0%
    tracker.record_usage(input_tokens=10000, output_tokens=1000, cached_tokens=5000)
    assert pytest.approx(tracker.get_cache_hit_rate(), 0.01) == 50.0

    # 10,000 cached out of 10,000 total prompt tokens = 100.0%
    tracker.reset()
    tracker.record_usage(input_tokens=10000, output_tokens=1000, cached_tokens=10000)
    assert pytest.approx(tracker.get_cache_hit_rate(), 0.01) == 100.0


def test_prompt_cache_tracker_hit_rate_invariant_no_double_counting():
    """Invariant: total_input_tokens represents total prompt tokens.
    Hit rate must be total_cache_read_tokens / total_input_tokens (0.0 to 1.0)."""
    tracker = PromptCacheTracker()

    tracker.record_turn(model_name="claude-3-5-sonnet", input_tokens=10000, cached_tokens=5000)
    assert pytest.approx(tracker.get_hit_rate(), 0.001) == 0.50

    tracker = PromptCacheTracker()
    tracker.record_turn(model_name="claude-3-5-sonnet", input_tokens=10000, cached_tokens=10000)
    assert pytest.approx(tracker.get_hit_rate(), 0.001) == 1.00


def test_deepseek_miss_tokens_not_mapped_to_cache_creation():
    """DeepSeek prompt_cache_miss_tokens represents uncached tokens, NOT cache creation tokens."""
    # Test dictionary usage (OpenRouter/DeepSeek dict)
    usage_dict = {
        "prompt_tokens": 4000,
        "completion_tokens": 200,
        "prompt_cache_hit_tokens": 3500,
        "prompt_cache_miss_tokens": 500,
    }
    inp, outp, cached, thinking, exact_cost, cache_creation = OpenAIProvider._extract_usage(usage_dict)
    assert inp == 4000
    assert outp == 200
    assert cached == 3500
    assert cache_creation == 0, f"Expected cache_creation=0 for DeepSeek, got {cache_creation}"

    # Test object usage (OpenAI client object)
    usage_obj = MagicMock()
    usage_obj.prompt_tokens = 4000
    usage_obj.completion_tokens = 200
    usage_obj.prompt_tokens_details = None
    usage_obj.prompt_cache_hit_tokens = 3500
    usage_obj.prompt_cache_miss_tokens = 500
    usage_obj.completion_tokens_details = None
    usage_obj.total_cost = None
    usage_obj.cost = None
    usage_obj.model_extra = None

    inp_o, outp_o, cached_o, thinking_o, cost_o, creation_o = OpenAIProvider._extract_usage(usage_obj)
    assert inp_o == 4000
    assert outp_o == 200
    assert cached_o == 3500
    assert creation_o == 0, f"Expected cache_creation=0 for DeepSeek object, got {creation_o}"


@pytest.mark.asyncio
async def test_deepseek_streaming_includes_stream_options():
    """DeepSeek streaming must include stream_options={'include_usage': True} to avoid telemetry blackout."""
    provider = OpenAIProvider(
        model="deepseek-chat",
        api_key="test-key",
        settings={"llm": {"deepseek": {"streaming": {"enabled": True}}}},
    )
    captured_kwargs = {}

    async def mock_call(kwargs):
        captured_kwargs.update(kwargs)
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        return mock_resp

    provider.client = MagicMock()
    with patch.object(provider, "_call_chat_completions_with_recovery", side_effect=mock_call):
        await provider._create_chat_completion({"messages": [{"role": "user", "content": "hi"}]})

    assert captured_kwargs.get("stream") is True
    assert captured_kwargs.get("stream_options") == {"include_usage": True}, (
        f"stream_options missing or incorrect for deepseek: {captured_kwargs.get('stream_options')}"
    )


@pytest.mark.asyncio
async def test_anthropic_cache_creation_accounting():
    """Anthropic input_tokens must include cache_creation_input_tokens so cold-cache prompt tokens are not dropped."""
    provider = AnthropicProvider(
        model="claude-3-5-sonnet",
        settings={"llm": {"providers": {"anthropic": {"streaming": {"enabled": False}}}}},
    )

    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.input = {"result": "ok"}
    mock_response.content = [mock_block]
    mock_response.stop_reason = "tool_use"
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 50
    mock_response.usage.output_tokens = 200
    mock_response.usage.cache_read_input_tokens = 0
    mock_response.usage.ephemeral_1h_input_tokens = 0
    mock_response.usage.cache_creation_input_tokens = 3500
    mock_response.usage.output_tokens_details = None

    saved_calls = []

    async def mock_save(*args, **kwargs):
        saved_calls.append({"args": args, "kwargs": kwargs})

    provider.client = MagicMock()
    provider.client.messages.create = AsyncMock(return_value=mock_response)

    with (
        patch.object(provider, "_save_token_usage", side_effect=mock_save),
        patch("monika.infrastructure.providers.anthropic_provider.ClaudeRateLimiter.acquire_session_slot", AsyncMock()),
    ):
        await provider.classify_json("test prompt", schema={"type": "object"})

    assert len(saved_calls) == 1
    call = saved_calls[0]
    # args: (model, task_name, inp, outp)
    model, task_name, inp, outp = call["args"][:4]
    # 50 uncached + 0 read + 3500 created = 3550 total prompt tokens
    assert inp == 3550, f"Expected normalized input_tokens=3550 (50 uncached + 3500 cache_create), got {inp}"
    assert call["kwargs"].get("cache_creation_tokens") == 3500


def test_base_provider_infer_task_role_loose_classify_removed():
    """classify_json must NOT be misattributed to news_classification when task_role is absent."""
    # classify_json without role should fall back to default
    assert BaseLLMClient._infer_task_role(None, "classify_json", None) == "default"
    assert BaseLLMClient._infer_task_role(None, "classify", None) == "default"

    # Only explicit news_class should resolve to news_classification
    assert BaseLLMClient._infer_task_role(None, "news_classification", None) == "news_classification"
    assert BaseLLMClient._infer_task_role(None, "news_class_worker", None) == "news_classification"


@pytest.mark.asyncio
async def test_typesafe_provider_explicit_task_role_and_latency():
    """TypeSafeProvider._call_openrouter_decisions path must pass task_role and execution_time_ms."""
    provider = TypeSafeProvider(
        model="luna-decision",
        settings={"llm": {"typesafe": {"api_key": "test"}}},
        role="stage1_shadow_check",
    )

    mock_resp = MagicMock()
    mock_resp.usage = MagicMock()
    mock_resp.usage.input_tokens = 100
    mock_resp.usage.output_tokens = 10
    mock_resp.usage.cached_tokens = 0
    mock_resp.usage.prompt_tokens_details = None

    saved_calls = []

    async def mock_save(*args, **kwargs):
        saved_calls.append({"args": args, "kwargs": kwargs})

    with (
        patch.object(provider, "_call_openrouter_decisions", AsyncMock(return_value=mock_resp)),
        patch.object(provider, "_save_token_usage", side_effect=mock_save),
        patch(
            "monika.infrastructure.providers.typesafe_provider.parse_jev_response_to_dict", return_value={"ok": True}
        ),
    ):
        await provider.classify_json(
            prompt="test",
            state="test state",
            schema={"type": "object", "properties": {"signal": {"type": "string"}}},
        )

    assert len(saved_calls) == 1
    kwargs = saved_calls[0]["kwargs"]
    assert kwargs.get("task_role") == "stage1_shadow_check", (
        f"Expected task_role='stage1_shadow_check', got {kwargs.get('task_role')}"
    )
    assert "execution_time_ms" in kwargs, f"Expected execution_time_ms in kwargs, got keys: {list(kwargs.keys())}"


@pytest.mark.asyncio
async def test_agent_harness_explicit_task_role_attribution():
    """AgentHarness must explicitly pass task_role to _save_token_usage."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.role = "stage1_fundamental"
    mock_client.model = "gemini-3.5-flash-lite"
    mock_client.provider_name = "gemini"
    mock_client._save_token_usage = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.usage = MagicMock()
    mock_resp.usage.input_tokens = 100
    mock_resp.usage.output_tokens = 20
    mock_resp.usage.cached_tokens = 10
    mock_resp.usage.prompt_tokens_details = None
    mock_resp.choices = [MagicMock(message=MagicMock(content="Analysis complete.", tool_calls=None))]

    mock_client.run_tool_agent = AsyncMock(return_value=mock_resp)

    harness = AgentHarness(
        llm_client=mock_client,
        settings={"harness": {"max_turns": 1}},
    )

    with patch.object(harness.compactor, "emergency_compact", side_effect=lambda msgs, **kw: msgs):
        res = await harness.run_agent_from_messages(
            session=None,
            system_prompt="system prompt",
            messages=[{"role": "user", "content": "analyze EURUSD"}],
            stage_name="stage1_fundamental",
            tools=[],
        )

    assert mock_client._save_token_usage.called, "_save_token_usage was not called by AgentHarness"
    call_kwargs = mock_client._save_token_usage.call_args.kwargs
    assert call_kwargs.get("task_role") == "stage1_fundamental", (
        f"Expected task_role='stage1_fundamental', got {call_kwargs.get('task_role')}"
    )
