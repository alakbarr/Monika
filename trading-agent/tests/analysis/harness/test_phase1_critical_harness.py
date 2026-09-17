"""
Unit tests for Critical Harness Protections (C1, C2, C3, M5, I2, I7).
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.harness.agent_harness import AgentHarness
from analysis.providers.base_provider import BaseLLMClient, MockResponse, MockBlock


class DummyHarnessClient(BaseLLMClient):
    """Test client subclassing BaseLLMClient for testing AgentHarness."""
    def __init__(self, model="dummy-model", **kwargs):
        super().__init__(model=model, max_tokens=4096, **kwargs)
        self.provider_name = "dummy"
        self._save_token_usage = AsyncMock()
        self.mock_run_tool_agent = AsyncMock()

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "text"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None, max_tokens=None):
        return {}

    async def run_tool_agent(self, messages: list, tools: list, system_prompt=None):
        return await self.mock_run_tool_agent(messages, tools, system_prompt)

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {"reply": "ok"}



@pytest.fixture
def mock_session():
    s = AsyncMock()
    s.add = MagicMock()
    return s


@pytest.mark.asyncio
async def test_c1_truncated_tool_call_protection(mock_session):
    """C1: Truncated tool call (stop_reason=max_tokens) refuses execution and requests re-generation."""
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=4)

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})

    # First turn: response truncated by max_tokens with a tool_use block
    resp1 = MockResponse(
        content=[MockBlock("tool_use", name="get_price_history", input={"symbol": "EURUSD"}, id="call_trunc_1")],
        stop_reason="max_tokens",
        input_tokens=50,
        output_tokens=100,
    )
    # Second turn: clean completion
    resp2 = MockResponse(
        content=[MockBlock("text", text="Finished recovery after truncation.")],
        stop_reason="end_turn",
        input_tokens=80,
        output_tokens=30,
    )
    client.mock_run_tool_agent.side_effect = [resp1, resp2]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="System",
        messages=[{"role": "user", "content": "Analyze market"}],
        tools=[],
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    # mock_executor.execute MUST NOT be called because the call was truncated!
    assert mock_executor.execute.call_count == 0

    # Verify corrective feedback was injected into context
    tool_results = [
        b["content"] for m in result["context_messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"] if b.get("type") == "tool_result"
    ]
    assert any("truncated" in str(c).lower() for c in tool_results)


@pytest.mark.asyncio
async def test_c2_context_overflow_auto_recovery(mock_session):
    """C2: Context overflow exception triggers emergency compaction and retries."""
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=4)

    # First call: context overflow error
    # Second call: success
    resp_success = MockResponse(
        content=[MockBlock("text", text="Recovery successful.")],
        stop_reason="end_turn",
        input_tokens=200,
        output_tokens=30,
    )
    client.mock_run_tool_agent.side_effect = [
        Exception("maximum context length is 8192 tokens, but request has 9200 tokens"),
        resp_success
    ]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="System",
        messages=[
            {"role": "user", "content": "User question"},
            {"role": "assistant", "content": "Assistant observation 1"},
            {"role": "user", "content": "Tool observation 2: " + "data " * 100},
        ],
        tools=[],
    )

    assert result["success"] is True
    assert client.mock_run_tool_agent.call_count == 2


@pytest.mark.asyncio
async def test_c3_copy_on_write_message_protection(mock_session):
    """C3: Provider client mutating the passed messages list cannot corrupt harness history."""
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=3)

    def mutating_run_tool_agent(msgs, tools, system_prompt):
        # Client mutates the msgs array
        msgs.append({"role": "user", "content": "MUTATION_INJECTION"})
        if msgs and isinstance(msgs[0], dict):
            msgs[0]["content"] = "CORRUPTED"
        return MockResponse(
            content=[MockBlock("text", text="Done")],
            stop_reason="end_turn",
            input_tokens=50,
            output_tokens=20,
        )

    client.mock_run_tool_agent.side_effect = mutating_run_tool_agent

    orig_messages = [{"role": "user", "content": "Original user content"}]
    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="System",
        messages=orig_messages,
        tools=[],
    )

    assert result["success"] is True
    # The original message in harness context must NOT be corrupted
    first_msg = result["context_messages"][0]
    assert first_msg["content"] == "Original user content"
    # MUTATION_INJECTION should NOT be in context_messages
    assert not any(m.get("content") == "MUTATION_INJECTION" for m in result["context_messages"])


@pytest.mark.asyncio
async def test_m5_preflight_tool_schema_validation(mock_session):
    """M5: Tool call missing required fields gets rejected preflight without executing."""
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=4)

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"ok": True})
    # Provide schema requiring 'symbol'
    mock_executor.get_tool_schema = MagicMock(return_value={
        "name": "calc_tool",
        "input_schema": {
            "type": "object",
            "required": ["symbol"],
            "properties": {"symbol": {"type": "string"}}
        }
    })

    resp1 = MockResponse(
        content=[MockBlock("tool_use", name="calc_tool", input={"wrong_key": 123}, id="c_schema_1")],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=20,
    )
    resp2 = MockResponse(
        content=[MockBlock("text", text="Done")],
        stop_reason="end_turn",
        input_tokens=50,
        output_tokens=20,
    )
    client.mock_run_tool_agent.side_effect = [resp1, resp2]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="System",
        messages=[{"role": "user", "content": "Start"}],
        tools=[],
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    # mock_executor.execute must NOT be called for the invalid schema
    assert mock_executor.execute.call_count == 0

    tool_results = [
        b["content"] for m in result["context_messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"] if b.get("type") == "tool_result"
    ]
    assert any("schema_validation_error" in str(c) or "required" in str(c).lower() for c in tool_results)


@pytest.mark.asyncio
async def test_c2_truncation_guard_length_finish_reason(mock_session):
    """C2: Truncated response with finish_reason='length' refuses tool calls."""
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=3)

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})

    resp1 = MockResponse(
        content=[MockBlock("tool_use", name="get_macro_data", input={"key": "val"}, id="call_len_1")],
        stop_reason="length",
        input_tokens=100,
        output_tokens=2048,
    )
    resp2 = MockResponse(
        content=[MockBlock("text", text="Completed after truncation correction.")],
        stop_reason="stop",
        input_tokens=120,
        output_tokens=50,
    )
    client.mock_run_tool_agent.side_effect = [resp1, resp2]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="System",
        messages=[{"role": "user", "content": "Analyze macro"}],
        tools=[],
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    assert mock_executor.execute.call_count == 0


@pytest.mark.asyncio
async def test_c1_persist_before_execute_event(mock_session):
    """C1: Pre-execute turn is persisted before tools are dispatched."""
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=3)

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"price": 1.0850})

    resp1 = MockResponse(
        content=[MockBlock("tool_use", name="get_price", input={"symbol": "EURUSD"}, id="call_p_1")],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=50,
    )
    resp2 = MockResponse(
        content=[MockBlock("text", text="Analysis complete")],
        stop_reason="end_turn",
        input_tokens=60,
        output_tokens=30,
    )
    client.mock_run_tool_agent.side_effect = [resp1, resp2]

    with patch("database.event_store.TradingEventStore.emit", new_callable=AsyncMock) as mock_emit:
        result = await harness.run_agent_from_messages(
            session=mock_session,
            system_prompt="System",
            messages=[{"role": "user", "content": "Fetch EURUSD"}],
            tools=[],
            tool_executor=mock_executor,
            stage_name="general",
            cycle_id="cycle_test_123",
        )

        assert result["success"] is True
        assert mock_emit.call_count >= 1
        call_kwargs = mock_emit.call_args_list[0].kwargs
        assert call_kwargs["event_type"] == "agent.turn.pre_execute"
        assert call_kwargs["correlation_id"] == "cycle_test_123"
        assert call_kwargs["payload"]["turn_index"] == 1
        assert len(call_kwargs["payload"]["tool_calls"]) == 1


def test_c4_role_alternation_enforcement():
    """C4: Verify _enforce_role_alternation repairs malformed message sequences."""
    # 1. Consecutive assistant messages
    msgs1 = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Step 1"},
        {"role": "assistant", "content": "Step 2"},
    ]
    repaired1 = AgentHarness._enforce_role_alternation(msgs1)
    roles1 = [m["role"] for m in repaired1]
    assert roles1 == ["user", "assistant", "user", "assistant"]
    assert "[System: Continue with your analysis.]" in repaired1[2]["content"]

    # 2. Consecutive user messages (strings)
    msgs2 = [
        {"role": "user", "content": "Part 1"},
        {"role": "user", "content": "Part 2"},
        {"role": "assistant", "content": "Acknowledged"},
    ]
    repaired2 = AgentHarness._enforce_role_alternation(msgs2)
    roles2 = [m["role"] for m in repaired2]
    assert roles2 == ["user", "assistant"]
    assert "Part 1\n\nPart 2" in repaired2[0]["content"]

    # 3. Valid sequence left untouched
    msgs3 = [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]
    repaired3 = AgentHarness._enforce_role_alternation(msgs3)
    assert [m["role"] for m in repaired3] == ["user", "assistant", "user", "assistant"]

    # 4. Leading assistant message prepended with user placeholder
    msgs4 = [
        {"role": "assistant", "content": "Initial assistant turn"},
    ]
    repaired4 = AgentHarness._enforce_role_alternation(msgs4)
    assert len(repaired4) == 2
    assert repaired4[0]["role"] == "user"
    assert repaired4[1]["role"] == "assistant"


def test_c2_truncation_openai_dict_format():
    """Verify truncation guard detects finish_reason='length' inside OpenAI dict choices."""
    resp = {
        "choices": [
            {"finish_reason": "length", "message": {"role": "assistant", "content": "Truncated"}}
        ]
    }
    assert AgentHarness._check_truncation(resp) is True


def test_c1_harness_db_session_init():
    """Verify AgentHarness accepts db_session in constructor."""
    mock_session = MagicMock()
    harness = AgentHarness(llm_client=MagicMock(), db_session=mock_session)
    assert harness.db_session is mock_session

