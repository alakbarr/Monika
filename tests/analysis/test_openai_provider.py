import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import create_mock_async_session
from monika.infrastructure.providers.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_generate():
    provider = OpenAIProvider(model="gpt-4o", api_key="test-key")

    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = "Hello from OpenAI"

    # We must patch the client inside the provider since it's already instantiated
    provider.client = AsyncMock()
    provider.client.chat.completions.create.return_value = mock_response

    result = await provider.generate("Say hello")
    assert result == "Hello from OpenAI"


@pytest.mark.asyncio
async def test_openai_classify_json():
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="test-key")

    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = json.dumps({"decision": "buy"})

    provider.client = AsyncMock()
    provider.client.chat.completions.create.return_value = mock_response

    result = await provider.classify_json("Is it buy?", {"type": "object"})
    assert result["decision"] == "buy"


def test_openai_normalize_messages_parallel_tools():
    provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
    anthropic_style_messages = [
        {"role": "user", "content": "Analyze markets"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Fetching indicators and price history"},
                {"type": "tool_use", "id": "call_1", "name": "get_dxy", "input": {}},
                {"type": "tool_use", "id": "call_2", "name": "get_vix", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "name": "get_dxy", "content": {"dxy": 104.5}},
                {"type": "tool_result", "tool_use_id": "call_2", "name": "get_vix", "content": {"vix": 14.2}},
            ],
        },
    ]
    normalized = provider._normalize_messages(anthropic_style_messages)
    assert len(normalized) == 4
    assert normalized[0]["role"] == "user"
    assert normalized[1]["role"] == "assistant"
    assert "tool_calls" in normalized[1]
    assert len(normalized[1]["tool_calls"]) == 2
    assert normalized[1]["tool_calls"][0]["id"] == "call_1"
    assert normalized[1]["tool_calls"][1]["id"] == "call_2"
    assert normalized[2]["role"] == "tool"
    assert normalized[2]["tool_call_id"] == "call_1"
    assert normalized[3]["role"] == "tool"
    assert normalized[3]["tool_call_id"] == "call_2"


@pytest.mark.asyncio
async def test_openai_token_logging():
    provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
    mock_usage = AsyncMock()
    mock_usage.prompt_tokens = 120
    mock_usage.completion_tokens = 45

    mock_response = AsyncMock()
    mock_response.usage = mock_usage
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = "Analysis output"

    provider.client = AsyncMock()
    provider.client.chat.completions.create.return_value = mock_response

    with patch.object(provider, "_save_token_usage", new_callable=AsyncMock) as mock_save:
        res = await provider.generate("Test prompt")
        assert res == "Analysis output"
        mock_save.assert_called_once_with("gpt-4o", "generate", 120, 45)


def test_extract_and_parse_json_with_trailing_braces():
    from monika.infrastructure.providers.base_provider import extract_and_parse_json

    raw_text = """{
  "adjudication_rule_correctly_applied": true,
  "expected_outcome_per_rules": "wait",
  "mismatch_explanation": "",
  "verdict": "CONFIRM"
}

Explanation: The specialist biases and confidence inputs are empty ({}), meaning no specialist provided valid inputs."""
    parsed = extract_and_parse_json(raw_text)
    assert parsed is not None
    assert parsed["verdict"] == "CONFIRM"
    assert parsed["expected_outcome_per_rules"] == "wait"
    assert parsed["adjudication_rule_correctly_applied"] is True


def test_extract_and_parse_json_with_unescaped_quotes():
    from monika.infrastructure.providers.base_provider import extract_and_parse_json

    raw_text = """```json
{
  "has_contradictions": true,
  "contradictions": [
    {
      "section_a": "MACRO OVERVIEW",
      "section_b": "XAU Nuances",
      "claim_a": ""Jackson Hole (Fed Chair Kevin Warsh): The single most critical macro event"",
      "claim_b": ""Jackson Hole is completely priced in""
    }
  ]
}
```"""
    parsed = extract_and_parse_json(raw_text)
    assert parsed is not None
    assert parsed["has_contradictions"] is True
    assert len(parsed["contradictions"]) == 1
    assert "Jackson Hole" in parsed["contradictions"][0]["claim_a"]


def test_extract_and_parse_json_truncated_ox_alpha_log():
    from monika.infrastructure.providers.base_provider import extract_and_parse_json

    raw_text = """```json
{
  "has_contradictions": true,
  "contradictions": [
    {
      "section_a": "CURRENCY SIGNAL SUMMARY",
      "section_b": "AUD TRADING DIGEST (Currency-Specific Nuances)",
      "claim_a": "| AUD | BEARISH | MEDIUM | -1 | RBA minutes due T"""
    parsed = extract_and_parse_json(raw_text)
    assert parsed is not None
    assert parsed["has_contradictions"] is True
    assert len(parsed["contradictions"]) == 1
    assert "RBA minutes due T" in parsed["contradictions"][0]["claim_a"]


def test_extract_and_parse_json_truncated_nested_arrays():
    from monika.infrastructure.providers.base_provider import extract_and_parse_json

    raw_text = '{"status": "ok", "items": [{"id": 1, "name": "foo"}, {"id": 2, "name": "bar'
    parsed = extract_and_parse_json(raw_text)
    assert parsed is not None
    assert parsed["status"] == "ok"
    assert len(parsed["items"]) == 2
    assert parsed["items"][1]["name"] == "bar"


@pytest.mark.asyncio
async def test_openai_402_prompt_tokens_exceeded_fail_fast():
    provider = OpenAIProvider(model="z-ai/glm-5.2", api_key="test-key")
    error_msg = "Error code: 402 - {'error': {'message': 'Prompt tokens limit exceeded: 10354 > 2275'}}"

    with patch.object(provider.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = Exception(error_msg)

        res = await provider.generate("Test prompt")
        assert res is None
        # Must fail-fast: exactly 1 call, no futile retry
        assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_openai_run_agent_empty_and_none_choices_safety():
    provider = OpenAIProvider(model="ox-alpha", api_key="test-key")
    mock_session = create_mock_async_session()

    # Case 1: choices is None (the exact ox-alpha bug)
    mock_resp_none_choices = MagicMock()
    mock_resp_none_choices.choices = None
    mock_resp_none_choices.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_resp_none_choices
        result = await provider.run_agent(mock_session, "system prompt", "user msg", [], "test_stage")
        assert isinstance(result, dict)
        assert result["success"] is False
        assert "choices" in result["error"].lower()

    # Case 2: choices is [] (empty list)
    mock_resp_empty_choices = MagicMock()
    mock_resp_empty_choices.choices = []
    mock_resp_empty_choices.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_resp_empty_choices
        result = await provider.run_agent(mock_session, "system prompt", "user msg", [], "test_stage")
        assert isinstance(result, dict)
        assert result["success"] is False
        assert "choices" in result["error"].lower()

    # Case 3: choice message is None
    mock_choice_no_msg = MagicMock()
    mock_choice_no_msg.message = None
    mock_resp_no_msg = MagicMock()
    mock_resp_no_msg.choices = [mock_choice_no_msg]
    mock_resp_no_msg.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_resp_no_msg
        result = await provider.run_agent(mock_session, "system prompt", "user msg", [], "test_stage")
        assert isinstance(result, dict)
        assert result["success"] is False
        assert "message" in result["error"].lower()


@pytest.mark.asyncio
async def test_openai_run_chat_loop_and_from_messages_safety():
    provider = OpenAIProvider(model="ox-alpha", api_key="test-key")
    mock_session = create_mock_async_session()

    # Test run_chat_loop with choices = None
    mock_resp = MagicMock()
    mock_resp.choices = None
    mock_resp.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_resp
        chat_res = await provider.run_chat_loop("sys", [], "hi", [])
        assert chat_res["success"] is False

    # Test run_agent_from_messages with choices = []
    mock_resp_empty = MagicMock()
    mock_resp_empty.choices = []
    mock_resp_empty.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_resp_empty
        from_msg_res = await provider.run_agent_from_messages(mock_session, "sys", [], [])
        assert from_msg_res["success"] is False


@pytest.mark.asyncio
async def test_openai_run_agent_extra_context():
    provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
    mock_session = create_mock_async_session()

    mock_msg = MagicMock()
    mock_msg.content = "Analysis result"
    mock_msg.tool_calls = None
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_resp
        res = await provider.run_agent(
            mock_session,
            system_prompt="sys prompt",
            user_message="Analyze XAUUSD",
            tools=[],
            stage_name="test_stage",
            extra_context="H1 RSI: 65, D1 Trend: Bullish",
        )
        assert res["success"] is True
        assert res["final_text"] == "Analysis result"

        # Verify extra_context was appended properly in messages passed to run_tool_agent
        passed_messages = mock_run.call_args[0][0]
        assert passed_messages[0]["role"] == "user"
        assert "Analyze XAUUSD" in passed_messages[0]["content"]
        assert "--- Additional Context ---\nH1 RSI: 65, D1 Trend: Bullish" in passed_messages[0]["content"]


@pytest.mark.asyncio
async def test_openai_run_agent_from_messages_tool_tracking():
    provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
    mock_session = create_mock_async_session()

    # Turn 1: Assistant calls submit_asset_analysis tool
    mock_func = MagicMock()
    mock_func.name = "submit_asset_analysis"
    mock_func.arguments = json.dumps(
        {
            "symbol": "XAUUSD",
            "decision": "buy",
            "confidence": 0.85,
            "rationale": "Strong bullish breakout with structural confluence",
            "invalidation": "2600.0",
        }
    )

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_submit"
    mock_tool_call.function = mock_func

    mock_msg_1 = MagicMock()
    mock_msg_1.content = None
    mock_msg_1.tool_calls = [mock_tool_call]
    mock_choice_1 = MagicMock()
    mock_choice_1.message = mock_msg_1
    mock_resp_1 = MagicMock()
    mock_resp_1.choices = [mock_choice_1]
    mock_resp_1.usage = None

    # Turn 2: Assistant returns final text
    mock_msg_2 = MagicMock()
    mock_msg_2.content = "All done"
    mock_msg_2.tool_calls = None
    mock_choice_2 = MagicMock()
    mock_choice_2.message = mock_msg_2
    mock_resp_2 = MagicMock()
    mock_resp_2.choices = [mock_choice_2]
    mock_resp_2.usage = None

    with patch.object(provider, "run_tool_agent", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [mock_resp_1, mock_resp_2]
        with patch(
            "monika.application.analysis.tools.tool_executor.ToolExecutor.execute", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {"status": "ok"}
            with patch.object(provider, "_log_tool_call", new_callable=AsyncMock):
                res = await provider.run_agent_from_messages(
                    mock_session,
                    system_prompt="system",
                    messages=[{"role": "user", "content": "trade XAUUSD"}],
                    tools=[],
                    stage_name="per_asset_XAUUSD",
                )
                assert res["success"] is True
                assert res["tool_calls_made"] == 1
                assert res["turns"] == 2


@pytest.mark.asyncio
async def test_openai_classify_json_recovers_from_raw_xml_tool_call():
    """Reproduces production bug where openrouter/free model emits <dots_function_call> XML,
    and proves that attempt 1 injects critical correction and recovers when JSON is returned."""
    provider = OpenAIProvider(model="openrouter/free", api_key="test-key")
    provider.client = AsyncMock()

    xml_tool_call = (
        "<dots_function_call>\n"
        '<invoke name="get_market_quote">\n'
        '<parameter="symbol">GBPUSD\n'
        "</parameter>\n"
        "</invoke>\n"
        "</dots_function_call>"
    )
    valid_json = json.dumps({"agree": True, "disagreement_category": "none", "reason": "confluence verified"})

    captured_prompts = []

    async def fake_generate_content(sys_prompt, user_msg, response_schema=None, **kwargs):
        captured_prompts.append((sys_prompt, user_msg, response_schema))
        if len(captured_prompts) == 1:
            return xml_tool_call
        return valid_json

    with patch.object(provider, "generate_content", side_effect=fake_generate_content):
        result = await provider.classify_json(
            prompt="Trade proposal: GBPUSD",
            system_prompt="You are a skeptical second-opinion reviewer.",
            schema={"type": "object"},
        )

    assert result is not None
    assert result["agree"] is True
    assert result["reason"] == "confluence verified"
    assert len(captured_prompts) == 2

    # Verify attempt 1 prompt received the critical anti-tool-call correction
    attempt_1_user_msg = captured_prompts[1][1]
    assert "[CRITICAL CORRECTION]" in attempt_1_user_msg
    assert "Tools are NOT available in this evaluation mode" in attempt_1_user_msg
    assert "<dots_function_call>" in attempt_1_user_msg


@pytest.mark.asyncio
async def test_openai_classify_json_fails_closed_when_both_attempts_fail():
    """When both attempts fail to produce parseable JSON, classify_json returns None gracefully."""
    provider = OpenAIProvider(model="openrouter/free", api_key="test-key")
    provider.client = AsyncMock()

    xml_tool_call = '<dots_function_call><invoke name="get_market_quote"><parameter="symbol">GBPUSD</parameter></invoke></dots_function_call>'

    with patch.object(provider, "generate_content", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = xml_tool_call
        result = await provider.classify_json(
            prompt="Trade proposal: GBPUSD",
            system_prompt="You are a skeptical second-opinion reviewer.",
            schema={"type": "object"},
        )

    assert result is None
    assert mock_gen.call_count == 2


@pytest.mark.asyncio
async def test_openai_classify_json_defaults_schema_when_none():
    """When schema is None (e.g. from OutputVerifier), classify_json passes effective_schema to generate_content."""
    provider = OpenAIProvider(model="openrouter/free", api_key="test-key")
    provider.client = AsyncMock()

    captured_schema = []

    async def fake_generate_content(sys_prompt, user_msg, response_schema=None, **kwargs):
        captured_schema.append(response_schema)
        return json.dumps({"decision": "buy", "is_verified": True})

    with patch.object(provider, "generate_content", side_effect=fake_generate_content):
        result = await provider.classify_json(
            prompt="Fix decision",
            system_prompt="Output Verifier",
            schema=None,
        )

    assert result == {"decision": "buy", "is_verified": True}
    assert captured_schema == [{"type": "object"}]


@pytest.mark.asyncio
async def test_openrouter_free_strips_cache_anchor_padding():
    """When provider model is openrouter/free, cache anchor padding is stripped so free models only receive the clean role directive."""
    from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

    provider = OpenAIProvider(model="openrouter/free", api_key="test-key")
    provider.client = AsyncMock()

    raw_sys = "=== CLOSED-LOOP QUANTITATIVE RISK & VERIFICATION AUDITOR ===\nReview trading decision."
    padded_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_sys, model_name="gemini-3.5-flash-lite", provider_name="gemini", force=True
    )
    assert "=== ROLE DIRECTIVE ===" in padded_sys

    with patch.object(provider, "_create_chat_completion", new_callable=AsyncMock) as mock_create:
        choice = MagicMock()
        choice.message = MagicMock(role="assistant", content=json.dumps({"ok": True}))
        mock_resp = MagicMock(choices=[choice], usage=None)
        mock_create.return_value = mock_resp

        await provider.generate_content(
            system_prompt=padded_sys,
            user_message="Audit proposal",
            response_schema={"type": "object"},
        )

        assert mock_create.called
        call_kwargs = mock_create.call_args[0][0]
        sys_msg = [m for m in call_kwargs["messages"] if m["role"] == "system"][0]
        # Must only contain the clean role directive, NOT the 21,000 char anchor
        assert sys_msg["content"] == raw_sys
        assert "=== CANONICAL SYSTEM GOVERNANCE" not in sys_msg["content"]


def test_cache_breakpoint_manager_skips_openrouter_free():
    """CacheBreakpointManager never injects padding anchors into openrouter/free or :free models."""
    from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

    raw = "You are a second opinion reviewer."
    res1 = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw, model_name="openrouter/free", provider_name="openrouter", force=True
    )
    assert res1 == raw

    res2 = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw, model_name="google/gemini-2.0-flash-exp:free", provider_name="openrouter", force=True
    )
    assert res2 == raw

    assert CacheBreakpointManager.should_inject_anchor(model_name="openrouter/free", force=True) is False
    assert CacheBreakpointManager.should_inject_anchor(model_name="meta-llama/llama-3.3-70b:free", force=True) is False
