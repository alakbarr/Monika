"""
Unit tests for Replay Envelope, Tool Recovery, Adaptive Thinking, and Constrained Sampling.
Covers:
- Non-destructive unanswered tool call recovery (_close_unanswered_tool_calls)
- Model failover reasoning translation (transform_messages_for_target_model)
- Assistant consecutive role merge signature preservation
- Turn liveness watchdog abort on hang
- Adaptive thinking MAX bucket reachability & answer room clamping
- Constrained sampling strict schema optional field wrapping & keyword rejection
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from monika.application.agent.harness.harness_state import SteeringMessage
from monika.application.agent.harness.message_repair import (
    TOOL_NOT_STARTED_MSG,
    TOOL_OUTCOME_UNKNOWN_MSG,
    _close_unanswered_tool_calls,
    _merge_consecutive_roles,
    repair_message_history,
    transform_messages_for_target_model,
)
from monika.application.agent.turn_liveness import TurnLivenessWatchdog
from monika.infrastructure.llm.adaptive_thinking import (
    PerSymbolAdaptiveThinkingAllocator,
    QuantizedThinkingAllocator,
    clamp_thinking_budget_to_answer_room,
)
from monika.infrastructure.llm.constrained_sampling import (
    can_use_strict_schema,
    make_strict_json_schema,
)


def test_close_unanswered_tool_calls_anthropic_format():
    """Anthropic format: preserves assistant tool_use blocks and appends synthetic tool_result."""
    messages = [
        {"role": "user", "content": "Analyze technical indicators"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Dispatching technical indicators"},
                {"type": "tool_use", "id": "call_answered", "name": "get_quote", "input": {"symbol": "XAUUSD"}},
                {"type": "tool_use", "id": "call_interrupted", "name": "place_order", "input": {"volume": 0.1}},
                {"type": "tool_use", "id": "call_unstarted", "name": "get_atr", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_answered", "content": '{"price": 2650.0}'},
            ],
        },
    ]

    executed_ids = {"call_answered", "call_interrupted"}
    repaired = _close_unanswered_tool_calls(messages, executed_call_ids=executed_ids)

    # 1. Assistant message tool_use blocks MUST NOT be stripped
    asst_msg = repaired[1]
    tool_uses = [b for b in asst_msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
    assert len(tool_uses) == 3
    assert {u["id"] for u in tool_uses} == {"call_answered", "call_interrupted", "call_unstarted"}

    # 2. User message must contain synthetic error results
    user_msg = repaired[2]
    results = {
        b["tool_use_id"]: b for b in user_msg["content"] if isinstance(b, dict) and b.get("type") == "tool_result"
    }
    assert len(results) == 3
    assert results["call_answered"]["content"] == '{"price": 2650.0}'
    assert results["call_interrupted"]["content"] == TOOL_OUTCOME_UNKNOWN_MSG
    assert results["call_interrupted"]["is_error"] is True
    assert results["call_unstarted"]["content"] == TOOL_NOT_STARTED_MSG
    assert results["call_unstarted"]["is_error"] is True


def test_close_unanswered_tool_calls_openai_format():
    """OpenAI format: preserves tool_calls array and appends synthetic tool messages."""
    messages = [
        {"role": "user", "content": "Check market"},
        {
            "role": "assistant",
            "content": "Running checks",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "f1", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "f2", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
    ]

    repaired = repair_message_history(
        messages,
        close_unanswered=True,
        executed_call_ids={"call_1", "call_2"},
    )

    asst = [m for m in repaired if m.get("role") == "assistant"][0]
    # tool_calls must NOT be pruned
    assert len(asst["tool_calls"]) == 2

    tool_msgs = [m for m in repaired if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert tool_msgs[1]["tool_call_id"] == "call_2"
    assert tool_msgs[1]["content"] == TOOL_OUTCOME_UNKNOWN_MSG


def test_merge_consecutive_assistants_preserves_signatures():
    """Merging consecutive assistant messages preserves reasoning_content and signatures."""
    messages = [
        {
            "role": "assistant",
            "content": "First turn reasoning.",
            "reasoning_content": "Chain-of-thought part 1",
            "thinking_signature": "sig_abc_123",
            "_source_provider": "anthropic",
            "_source_model": "claude-3-7-sonnet",
        },
        {
            "role": "assistant",
            "content": "Second turn conclusion.",
            "reasoning_content": "Chain-of-thought part 2",
            "thought_signature": "thought_sig_xyz",
            "reasoning_details": [{"step": 2}],
        },
    ]

    merged = _merge_consecutive_roles(messages, "assistant")
    assert len(merged) == 1
    m = merged[0]
    assert "First turn reasoning.\n\nSecond turn conclusion." in m["content"]
    assert "Chain-of-thought part 1\n\nChain-of-thought part 2" in m["reasoning_content"]
    assert m["thinking_signature"] == "sig_abc_123"
    assert m["thought_signature"] == "thought_sig_xyz"
    assert m["reasoning_details"] == [{"step": 2}]
    assert m["_source_provider"] == "anthropic"


def test_transform_messages_for_target_model_same_target():
    """Replaying against the same provider and model keeps signed thinking blocks intact."""
    messages = [
        {
            "role": "assistant",
            "_source_provider": "anthropic",
            "_source_model": "claude-3-7-sonnet",
            "content": [
                {"type": "redacted_thinking", "data": "opaque_hash_blob"},
                {"type": "thinking", "thinking": "Internal deliberation", "signature": "crypto_sig_999"},
                {"type": "text", "text": "Final answer", "thoughtSignature": "ts_456"},
            ],
            "thinking_signature": "sig_main",
        }
    ]

    transformed = transform_messages_for_target_model(
        messages,
        target_provider="anthropic",
        target_model="claude-3-7-sonnet",
    )
    assert len(transformed) == 1
    asst = transformed[0]
    types = [b.get("type") for b in asst["content"]]
    assert "redacted_thinking" in types
    assert "thinking" in types
    assert asst.get("thinking_signature") == "sig_main"


def test_transform_messages_for_target_model_cross_model_failover():
    """Cross-model failover strips cryptographic signatures and converts thinking to text blocks."""
    messages = [
        {
            "role": "assistant",
            "_source_provider": "anthropic",
            "_source_model": "claude-3-7-sonnet",
            "content": [
                {"type": "redacted_thinking", "data": "opaque_hash_blob"},
                {"type": "thinking", "thinking": "Internal deliberation", "signature": "crypto_sig_999"},
                {"type": "text", "text": "Final answer", "thoughtSignature": "ts_456"},
            ],
            "thinking_signature": "sig_main",
            "thought_signature": "gemini_ts",
        }
    ]

    # Failing over to OpenAI / DeepSeek
    transformed = transform_messages_for_target_model(
        messages,
        target_provider="deepseek",
        target_model="deepseek-reasoner",
    )
    assert len(transformed) == 1
    asst = transformed[0]

    # Top-level signatures must be stripped
    assert "thinking_signature" not in asst
    assert "thought_signature" not in asst

    # Content: redacted_thinking stripped, thinking converted to plain text, signatures stripped
    content = asst["content"]
    types = [b.get("type") for b in content]
    assert "redacted_thinking" not in types
    assert "thinking" not in types

    texts = [b.get("text", "") for b in content if b.get("type") == "text"]
    assert any("[Prior reasoning]: Internal deliberation" in t for t in texts)
    assert any("Final answer" in t for t in texts)
    for b in content:
        assert "thoughtSignature" not in b
        assert "signature" not in b


@pytest.mark.asyncio
async def test_turn_liveness_watchdog_abort_on_hang():
    """Watchdog triggers cancel_event and aborts running task when abort_on_hang=True."""
    cancel_event = asyncio.Event()

    async def hung_workload():
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            return "aborted"

    work_task = asyncio.create_task(hung_workload())

    watchdog = TurnLivenessWatchdog(
        turn_id="test_abort_hang",
        timeout_seconds=0.1,
        check_interval_seconds=0.02,
        task_to_cancel=work_task,
        cancel_event=cancel_event,
        abort_on_hang=True,
    )

    watchdog.start()
    try:
        await asyncio.sleep(0.25)
        assert watchdog.hang_detected is True
        assert cancel_event.is_set() is True
        assert work_task.cancelled() or work_task.done()
    finally:
        watchdog.stop()


def test_adaptive_thinking_max_bucket_and_headroom_clamping():
    """Adaptive thinking reaches 16000 (MAX bucket) on high stress and clamps to answer headroom."""
    # 1. High volatility + high conflict + crisis setup
    ctx = {
        "vix": 35.0,  # vix_mult = 1.6
        "confluence_score": 6.5,  # conf_mult = 1.3
        "regime": "CRISIS_EVENT",  # regime_mult = 1.3
    }
    # BTCUSD asset_mult = 1.4
    # computed = 4000 * 1.4 * 1.6 * 1.3 * 1.3 = 15142 >= 13000 -> MAX bucket (16000)
    budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget("BTCUSD", context=ctx, base_budget=4000)
    assert budget == QuantizedThinkingAllocator.BUCKETS["MAX"]
    assert budget == 16000

    # 2. clamp_thinking_budget_to_answer_room
    # max_tokens = 8192, min_answer_tokens = 1024 -> max thinking allowed = 7168
    clamped = clamp_thinking_budget_to_answer_room(budget=10000, max_tokens=8192, min_answer_tokens=1024)
    assert clamped == 7168

    # When budget fits within headroom, it stays unchanged
    clamped_fit = clamp_thinking_budget_to_answer_room(budget=4096, max_tokens=8192, min_answer_tokens=1024)
    assert clamped_fit == 4096

    # Starved room: max_tokens <= min_answer_tokens returns 0
    clamped_starved = clamp_thinking_budget_to_answer_room(budget=2048, max_tokens=1024, min_answer_tokens=1024)
    assert clamped_starved == 0


def test_make_strict_json_schema_optional_wrapping_and_unsupported_keys():
    """Strict schema wraps optional fields in nullable anyOf and detects unsupported keys."""
    schema = {
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_field": {"type": "number", "default": 42},
        },
        "required": ["required_field"],
    }

    strict = make_strict_json_schema(schema)

    assert strict["additionalProperties"] is False
    assert set(strict["required"]) == {"required_field", "optional_field"}

    # required_field is not wrapped
    assert strict["properties"]["required_field"]["type"] == "string"
    assert "anyOf" not in strict["properties"]["required_field"]

    # optional_field is wrapped in nullable anyOf with default stripped
    opt_schema = strict["properties"]["optional_field"]
    assert "anyOf" in opt_schema
    assert opt_schema["anyOf"] == [{"type": "number"}, {"type": "null"}]
    assert "default" not in opt_schema["anyOf"][0]

    # Unsupported strict schema keywords detection
    assert can_use_strict_schema({"type": "object", "properties": {"a": {"type": "string"}}}) is True
    assert can_use_strict_schema({"$ref": "#/definitions/Foo"}) is False
    assert can_use_strict_schema({"type": "string", "minLength": 5}) is False
    assert can_use_strict_schema({"type": "object", "properties": {"b": {"oneOf": []}}}) is False


class _MockBlock:
    def __init__(self, block_type: str, **kwargs):
        self.type = block_type
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockResponse:
    def __init__(self, content, stop_reason="end_turn", input_tokens=100, output_tokens=50):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = type("Usage", (), {"prompt_tokens": input_tokens, "completion_tokens": output_tokens})()


def test_agent_harness_preserves_thinking_and_redacted_blocks_anthropic():
    """AgentHarness._normalize_response_content preserves ThinkingBlock and RedactedThinkingBlock."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.provider = "anthropic"
    mock_client.model = "claude-3-7-sonnet"
    harness = AgentHarness(mock_client)

    content = [
        _MockBlock("thinking", thinking="Deep deliberation on macro stance", signature="sig_crypto_789"),
        _MockBlock("redacted_thinking", data="opaque_redacted_blob"),
        _MockBlock("text", text="Market outlook conclusion"),
    ]
    resp = _MockResponse(content)

    blocks, stop_reason, reasoning, in_tok, out_tok, c_tok, th_tok = harness._normalize_response_content(resp)

    types = [b.get("type") for b in blocks]
    assert types == ["thinking", "redacted_thinking", "text"]

    thinking_b = blocks[0]
    assert thinking_b["thinking"] == "Deep deliberation on macro stance"
    assert thinking_b["signature"] == "sig_crypto_789"

    redacted_b = blocks[1]
    assert redacted_b["data"] == "opaque_redacted_blob"


def test_agent_harness_preserves_openai_and_gemini_signatures():
    """AgentHarness preserves thought_signature, reasoning_details, and extra_content on choice.message."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.provider = "openai"
    mock_client.model = "o3-mini"
    harness = AgentHarness(mock_client)

    msg = MagicMock()
    msg.content = "Analysis completed"
    msg.reasoning_content = "Chain of thought steps"
    msg.tool_calls = []
    msg.thought_signature = "sig_thought_gemini_999"
    msg.reasoning_details = [{"step": 1, "thought": "Evaluate yield spreads"}]
    msg.model_extra = {"extra_content": "extra_opaque_metadata"}

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.content = None
    del resp.content  # Ensure has_content is False
    resp.usage = MagicMock(prompt_tokens=150, completion_tokens=80)

    blocks, stop_reason, reasoning, in_tok, out_tok, c_tok, th_tok = harness._normalize_response_content(resp)

    assert hasattr(harness, "_last_normalized_extra")
    extra = harness._last_normalized_extra
    assert extra.get("thought_signature") == "sig_thought_gemini_999"
    assert extra.get("reasoning_details") == [{"step": 1, "thought": "Evaluate yield spreads"}]
    assert extra.get("extra_content") == "extra_opaque_metadata"


@pytest.mark.asyncio
async def test_agent_harness_fallback_swap_and_signature_transformation():
    """Failover swaps client and calls transform_messages_for_target_model to strip foreign signatures."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    primary_client = MagicMock()
    primary_client.provider = "anthropic"
    primary_client.model = "claude-3-7-sonnet"
    primary_client.run_tool_agent = AsyncMock(return_value=None)  # Fails

    fallback_client = MagicMock()
    fallback_client.provider = "openai"
    fallback_client.model = "gpt-4o"
    fb_resp = _MockResponse([_MockBlock("text", text="Recovery output from fallback")])
    fallback_client.run_tool_agent = AsyncMock(return_value=fb_resp)

    harness = AgentHarness(primary_client, fallback_client=fallback_client, max_tool_turns=3)

    initial_messages = [
        {"role": "user", "content": "Analyze currency pairs"},
        {
            "role": "assistant",
            "_source_provider": "anthropic",
            "_source_model": "claude-3-7-sonnet",
            "content": [
                {"type": "thinking", "thinking": "Internal thoughts", "signature": "foreign_crypto_sig"},
                {"type": "text", "text": "Preliminary observation"},
            ],
        },
    ]

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="Trading system",
        messages=initial_messages,
        tools=[],
        stage_name="test_fallback",
    )

    assert result["success"] is True
    assert harness.llm_client is fallback_client
    # Messages sent to fallback have had foreign signatures converted cleanly
    context_msgs = result["context_messages"]
    asst_msg = context_msgs[1]
    assert asst_msg["role"] == "assistant"
    # No raw thinking block with foreign signature remains in assistant content
    for b in asst_msg.get("content", []):
        if isinstance(b, dict):
            assert "signature" not in b
            assert b.get("type") != "thinking"


@pytest.mark.asyncio
async def test_agent_harness_outer_follow_up_queue_turn_extension():
    """Follow-up queue message on last turn extends effective_max_turns rather than being dropped."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.provider = "openai"
    mock_client.model = "gpt-4o"

    # Turn 1: text conclusion.
    # Turn 2: response to follow-up task.
    resp1 = _MockResponse([_MockBlock("text", text="Turn 1 done")])
    resp2 = _MockResponse([_MockBlock("text", text="Turn 2 follow-up response completed")])
    mock_client.run_tool_agent = AsyncMock(side_effect=[resp1, resp2])

    harness = AgentHarness(mock_client, max_tool_turns=1)
    harness._follow_up_queue.append(SteeringMessage(sender="supervisor", content="Verify liquidity sweep"))

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="System",
        messages=[{"role": "user", "content": "Start"}],
        tools=[],
        stage_name="test_followup",
    )

    assert result["success"] is True
    # mock_client was called twice because effective_max_turns was incremented!
    assert mock_client.run_tool_agent.call_count == 2
    # Verify the follow up task message was recorded
    history_texts = [m.get("content") for m in result["context_messages"] if isinstance(m.get("content"), str)]
    assert any("[SUPERVISOR FOLLOW-UP TASK]: Verify liquidity sweep" in t for t in history_texts)


@pytest.mark.asyncio
async def test_agent_harness_populates_stop_gate_context():
    """Tool execution updates turn_state.stop_gate_context (mutated_files and verification_commands_run)."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.provider = "openai"
    mock_client.model = "gpt-4o"

    # Turn 1: patch file. Turn 2: run pytest. Turn 3: conclude.
    resp1 = _MockResponse(
        [_MockBlock("tool_use", id="c1", name="patch_source_file", input={"filepath": "src/fix.py", "diff": "..."})],
        stop_reason="tool_use",
    )
    resp2 = _MockResponse(
        [_MockBlock("tool_use", id="c2", name="run_verification_gate", input={"gate": "pytest"})],
        stop_reason="tool_use",
    )
    resp3 = _MockResponse([_MockBlock("text", text="All changes verified.")], stop_reason="end_turn")
    mock_client.run_tool_agent = AsyncMock(side_effect=[resp1, resp2, resp3])

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(side_effect=[{"status": "patched"}, {"status": "all_passed"}])

    harness = AgentHarness(mock_client, max_tool_turns=4)

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="System",
        messages=[{"role": "user", "content": "Fix bug"}],
        tools=[{"name": "patch_source_file"}, {"name": "run_verification_gate"}],
        tool_executor=mock_executor,
        stage_name="test_stop_gate_context",
    )

    assert result["success"] is True
    assert mock_executor.execute.call_count == 2


@pytest.mark.asyncio
async def test_agent_harness_load_tool_category_activation():
    """Executing load_tool_category appends new tool definitions to active_tools in sorted order."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.provider = "openai"
    mock_client.model = "gpt-4o"

    # Turn 1: call load_tool_category. Turn 2: conclude.
    resp1 = _MockResponse(
        [_MockBlock("tool_use", id="c1", name="load_tool_category", input={"category": "crypto"})],
        stop_reason="tool_use",
    )
    resp2 = _MockResponse([_MockBlock("text", text="Tools loaded.")], stop_reason="end_turn")
    mock_client.run_tool_agent = AsyncMock(side_effect=[resp1, resp2])

    loaded_schemas = [
        {"name": "get_crypto_funding_rates", "description": "Fetch funding rates"},
        {"name": "get_crypto_orderbook", "description": "Fetch orderbook"},
    ]
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(
        return_value={
            "status": "success",
            "category": "crypto",
            "schemas": loaded_schemas,
        }
    )

    harness = AgentHarness(mock_client, max_tool_turns=3)
    base_tools = [{"name": "inspect_workspace"}]

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="System",
        messages=[{"role": "user", "content": "Load crypto tools"}],
        tools=base_tools,
        tool_executor=mock_executor,
        stage_name="test_load_category",
    )

    assert result["success"] is True
    # Second turn run_tool_agent call must have received the 2 new loaded tools in sorted order!
    call_args_turn2 = mock_client.run_tool_agent.call_args_list[1]
    turn2_tools = call_args_turn2[0][1]
    tool_names = [t["name"] for t in turn2_tools]
    assert tool_names == ["get_crypto_funding_rates", "get_crypto_orderbook", "inspect_workspace"]


@pytest.mark.asyncio
async def test_agent_harness_escalating_repeat_tool_reminder():
    """Repeat call at count 2 gets advisory reminder appended; hard-suppressed at count >= threshold."""
    from monika.application.agent.harness.agent_harness import AgentHarness

    mock_client = MagicMock()
    mock_client.provider = "openai"
    mock_client.model = "gpt-4o"

    # Turn 1: call query_rate.
    # Turn 2: repeat query_rate (gets advisory).
    # Turn 3: repeat query_rate again (hard suppressed at threshold 3).
    # Turn 4: conclude.
    resp1 = _MockResponse(
        [_MockBlock("tool_use", id="c1", name="query_rate", input={"symbol": "EURUSD"})], stop_reason="tool_use"
    )
    resp2 = _MockResponse(
        [_MockBlock("tool_use", id="c2", name="query_rate", input={"symbol": "EURUSD"})], stop_reason="tool_use"
    )
    resp3 = _MockResponse(
        [_MockBlock("tool_use", id="c3", name="query_rate", input={"symbol": "EURUSD"})], stop_reason="tool_use"
    )
    resp4 = _MockResponse([_MockBlock("text", text="Concluded")], stop_reason="end_turn")
    mock_client.run_tool_agent = AsyncMock(side_effect=[resp1, resp2, resp3, resp4])

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"price": 1.0850})

    harness = AgentHarness(
        mock_client,
        settings={"repeat_tool_suppress_threshold": 3},
        max_tool_turns=5,
    )

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="System",
        messages=[{"role": "user", "content": "Monitor rate"}],
        tools=[{"name": "query_rate"}],
        tool_executor=mock_executor,
        stage_name="test_escalating_repeat",
    )

    assert result["success"] is True
    # mock_executor was executed twice (turn 1 and turn 2); turn 3 was hard-suppressed
    assert mock_executor.execute.call_count == 2

    # Check that turn 2 tool result contains the advisory reminder
    tool_results = [
        b["content"]
        for m in result["context_messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]
    # One tool result contains advisory reminder
    assert any("[ADVISORY REMINDER:" in str(c) for c in tool_results)
    # One tool result contains already_executed hard suppression
    assert any("already_executed" in str(c) for c in tool_results)


def test_deep_repair_tool_arguments_metadata_and_strict_validation():
    """deep_repair_tool_arguments records _repaired_missing_fields and respects strict_validation."""
    from monika.application.agent.harness.tool_repair import deep_repair_tool_arguments

    schema = {
        "type": "object",
        "properties": {
            "macro_narrative": {"type": "string"},
            "symbol": {"type": "string"},
        },
        "required": ["macro_narrative", "symbol"],
    }
    error_msg = "'macro_narrative' is a required property"

    # 1. Non-strict mode: fabricates fallback and records metadata
    args_lenient = {"symbol": "EURUSD"}
    healed = deep_repair_tool_arguments(
        "submit_fundamental_brief",
        args_lenient,
        schema,
        error_msg,
        strict_validation=False,
    )
    assert healed is True
    assert "macro_narrative" in args_lenient
    assert args_lenient.get("_repaired_missing_fields") == ["macro_narrative"]

    # 2. Strict mode: does NOT fabricate analytical text fields and returns False
    args_strict = {"symbol": "EURUSD"}
    healed_strict = deep_repair_tool_arguments(
        "submit_fundamental_brief",
        args_strict,
        schema,
        error_msg,
        strict_validation=True,
    )
    assert healed_strict is False
    assert "macro_narrative" not in args_strict


@pytest.mark.asyncio
async def test_chat_agent_tiers_static_tool_ordering():
    """ChatAgent tiers sort selected_tools canonically by name for KV cache invariance."""
    from monika.application.agent.chat.tiers import ExecutionTiersMixin

    agent = ExecutionTiersMixin()
    agent.settings = {}
    agent._tool_router = MagicMock()
    # Return tools in reverse alphabetical order
    agent._tool_router.route_tools_for_query = MagicMock(
        return_value=[
            {"name": "zebra_scanner"},
            {"name": "alpha_finder"},
            {"name": "beta_rater"},
        ]
    )
    agent._build_lean_system_prompt = MagicMock(return_value="lean prompt")
    agent._format_user_message_payload = MagicMock(return_value="user payload")

    mock_lite_client = MagicMock()
    mock_lite_client.run_chat_loop = AsyncMock(return_value={"reply": "ok"})
    agent._client_lite = mock_lite_client

    await agent._run_tier_lite(system_prompt="sys", history=[], message="Check market")

    call_kwargs = mock_lite_client.run_chat_loop.call_args.kwargs
    passed_tools = call_kwargs["tools"]
    tool_names = [t["name"] for t in passed_tools]
    # Tools must be sorted canonically by name!
    assert tool_names == ["alpha_finder", "beta_rater", "zebra_scanner"]
