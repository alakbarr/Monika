import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.harness.agent_harness import AgentHarness
from analysis.providers.base_provider import BaseLLMClient, MockResponse, MockBlock


class DummyLLMClient(BaseLLMClient):
    """Minimal test client subclassing BaseLLMClient."""
    def __init__(self, model="dummy-model", **kwargs):
        super().__init__(model=model, max_tokens=4096, **kwargs)
        self.provider_name = "dummy"
        self._save_token_usage = AsyncMock()
        self.mock_run_tool_agent = AsyncMock()

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "dummy_text"

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


@pytest.fixture
def dummy_client():
    return DummyLLMClient()


def test_harness_tool_signature_deterministic():
    """Verify deterministic hashing of tool name and parameter payloads."""
    sig1 = AgentHarness.compute_tool_signature("get_dxy", {"symbol": "DXY", "lookback": 5})
    sig2 = AgentHarness.compute_tool_signature("get_dxy", {"lookback": 5, "symbol": "DXY"})
    assert sig1 == sig2
    assert sig1.startswith("get_dxy:")

    sig3 = AgentHarness.compute_tool_signature("get_dxy", {"symbol": "EURUSD"})
    assert sig1 != sig3


def test_harness_mandatory_tool_detection():
    """Verify detection of mandatory concluding tools per stage."""
    assert AgentHarness.get_mandatory_tool_for_stage("per_asset_EURUSD") == "submit_asset_analysis"
    assert AgentHarness.get_mandatory_tool_for_stage("per_asset_primary") == "submit_asset_analysis"
    assert AgentHarness.get_mandatory_tool_for_stage("fundamental") == "submit_fundamental_brief"
    assert AgentHarness.get_mandatory_tool_for_stage("arbitration") is None


def test_harness_error_classification():
    """Verify transient error and billing error classifiers."""
    class ErrWithCode(Exception):
        def __init__(self, msg, code):
            super().__init__(msg)
            self.status_code = code

    # Transient
    assert AgentHarness._is_transient_error(ErrWithCode("rate limit hit", 429)) is True
    assert AgentHarness._is_transient_error(ErrWithCode("server overload", 529)) is True
    assert AgentHarness._is_transient_error(ErrWithCode("bad gateway", 502)) is True
    assert AgentHarness._is_transient_error(Exception("Connection error: temporarily unavailable")) is True
    assert AgentHarness._is_transient_error(Exception("Normal syntax error")) is False

    # Billing
    assert AgentHarness._is_billing_error(ErrWithCode("Payment Required", 402)) is True
    assert AgentHarness._is_billing_error(Exception("Your credit balance is too low")) is True
    assert AgentHarness._is_billing_error(Exception("insufficient_quota error")) is True
    assert AgentHarness._is_billing_error(Exception("Normal syntax error")) is False
    assert AgentHarness._is_billing_error(None) is False


def test_harness_normalize_response_anthropic(dummy_client):
    """Verify normalization of Anthropic-style content blocks."""
    harness = AgentHarness(dummy_client)
    mock_resp = MockResponse(
        content=[
            MockBlock("text", text="Thinking about price action..."),
            MockBlock("tool_use", name="get_ohlcv", input={"symbol": "EURUSD"}, id="call_123"),
        ],
        stop_reason="tool_use",
        input_tokens=100,
        output_tokens=50,
        thinking_tokens=15,
        cached_tokens=20,
    )

    blocks, stop_reason, reasoning, in_tok, out_tok, cached_tok, thinking_tok = (
        harness._normalize_response_content(mock_resp)
    )

    assert stop_reason == "tool_use"
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"] == "Thinking about price action..."
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["name"] == "get_ohlcv"
    assert blocks[1]["id"] == "call_123"
    assert in_tok == 100
    assert out_tok == 50
    assert cached_tok == 20
    assert thinking_tok == 15


def test_harness_normalize_response_openai(dummy_client):
    """Verify normalization of OpenAI ChatCompletion response structure."""
    dummy_client.provider_name = "openai"
    harness = AgentHarness(dummy_client)

    class OpenAIMessage:
        content = "Analysis complete"
        reasoning_content = "Evaluated trend and volume"
        mock_fn = MagicMock()
        mock_fn.name = "get_sentiment"
        mock_fn.arguments = json.dumps({"asset": "EUR"})
        tool_calls = [MagicMock(id="call_999", function=mock_fn)]

    class OpenAIChoice:
        finish_reason = "tool_calls"
        message = OpenAIMessage()

    class OpenAIUsage:
        prompt_tokens = 250
        completion_tokens = 80
        prompt_tokens_details = MagicMock(cached_tokens=40)
        completion_tokens_details = MagicMock(reasoning_tokens=30)

    class OpenAIResponse:
        choices = [OpenAIChoice()]
        usage = OpenAIUsage()

    blocks, stop_reason, reasoning, in_tok, out_tok, cached_tok, thinking_tok = (
        harness._normalize_response_content(OpenAIResponse())
    )

    assert stop_reason == "tool_calls"
    assert reasoning == "Evaluated trend and volume"
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"] == "Analysis complete"
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["name"] == "get_sentiment"
    assert blocks[1]["input"] == {"asset": "EUR"}
    assert in_tok == 250
    assert out_tok == 80
    assert cached_tok == 40
    assert thinking_tok == 30


@pytest.mark.asyncio
async def test_harness_anti_oscillation_suppresses_repeated_calls(dummy_client, mock_session):
    """Verify that calling the same tool with identical inputs consecutively is suppressed."""
    harness = AgentHarness(dummy_client, max_tool_turns=5)

    # Mock tool executor
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"result": "data_1"})

    # First turn: call get_rate
    resp1 = MockResponse(
        content=[MockBlock("tool_use", name="get_rate", input={"symbol": "EURUSD"}, id="c1")],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=20,
    )
    # Second turn: call get_rate with same arguments (oscillation!)
    resp2 = MockResponse(
        content=[MockBlock("tool_use", name="get_rate", input={"symbol": "EURUSD"}, id="c2")],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=20,
    )
    # Third turn: end turn
    resp3 = MockResponse(
        content=[MockBlock("text", text="Conclusion reached")],
        stop_reason="end_turn",
        input_tokens=50,
        output_tokens=20,
    )

    dummy_client.mock_run_tool_agent.side_effect = [resp1, resp2, resp3]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="Analyze",
        messages=[{"role": "user", "content": "Start"}],
        tools=[{"name": "get_rate"}],
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    # mock_executor.execute should be called only once because turn 2 was suppressed
    assert mock_executor.execute.call_count == 1

    # Verify context_messages received the suppression payload
    tool_results = [
        b["content"] for m in result["context_messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"] if b.get("type") == "tool_result"
    ]
    # One of the tool results must contain "already_executed"
    assert any("already_executed" in str(c) for c in tool_results)


@pytest.mark.asyncio
async def test_harness_tool_family_quota_suppression(dummy_client, mock_session):
    """Verify that exceeding tool family quota triggers suppression notice."""
    settings = {
        "analysis": {
            "compaction": {
                "tool_quotas": {
                    "price_action": 1
                }
            }
        }
    }
    harness = AgentHarness(dummy_client, settings=settings, max_tool_turns=4)

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"price": 1.1000})

    # We mock compactor check_tool_family_quota: first call allowed, second call denied
    harness.compactor.check_tool_family_quota = MagicMock(side_effect=[(True, None), (False, "Quota of 1 reached for price_action")])

    resp1 = MockResponse(
        content=[MockBlock("tool_use", name="get_ohlcv", input={"count": 10}, id="c1")],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=20,
    )
    resp2 = MockResponse(
        content=[MockBlock("tool_use", name="get_tick", input={"symbol": "EURUSD"}, id="c2")],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=20,
    )
    resp3 = MockResponse(
        content=[MockBlock("text", text="Done")],
        stop_reason="end_turn",
        input_tokens=50,
        output_tokens=20,
    )

    dummy_client.mock_run_tool_agent.side_effect = [resp1, resp2, resp3]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="System",
        messages=[{"role": "user", "content": "Start"}],
        tools=[],
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    # Only first tool call was executed
    assert mock_executor.execute.call_count == 1

    tool_results = [
        b["content"] for m in result["context_messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"] if b.get("type") == "tool_result"
    ]
    assert any("quota_exceeded" in str(c) for c in tool_results)


def test_harness_state_preservation_truncation(dummy_client):
    """Verify that trimming large conversation histories preserves key numeric state facts."""
    harness = AgentHarness(dummy_client)
    harness.max_context_chars = 200

    messages = [
        {"role": "user", "content": "First instruction"},
        {"role": "assistant", "content": "Calling tool..."},
        {"role": "user", "content": [
            {
                "type": "tool_result",
                "content": json.dumps({
                    "atr_14": 0.0045,
                    "latest": {"close": 1.0850, "date": "2026-09-05"},
                    "trend_5d": "bullish"
                })
            }
        ]},
        {"role": "assistant", "content": "Tool processed"},
        {"role": "user", "content": "Next step"},
        {"role": "assistant", "content": "A" * 150},
        {"role": "user", "content": "B" * 150},
        {"role": "assistant", "content": "C" * 150},
        {"role": "user", "content": "D" * 150},
        {"role": "assistant", "content": "Recent observation"},
    ]

    trimmed = harness._apply_truncation_guardrail(messages, "System Prompt", "test_stage")

    # First user message must be preserved
    assert trimmed[0] == messages[0]

    # Summary block must contain extracted facts
    summary_msg = trimmed[1]
    assert summary_msg["role"] == "user"
    assert "CONTEXT WINDOW STATE SUMMARY" in summary_msg["content"]
    assert "ATR_14=0.0045" in summary_msg["content"]
    assert "Latest_Close=1.085 on 2026-09-05" in summary_msg["content"]
    assert "Trend_5d=bullish" in summary_msg["content"]


@pytest.mark.asyncio
async def test_harness_prompt_cache_hardening_with_tuple(mock_session, dummy_client):
    dummy_client.mock_run_tool_agent.return_value = MockResponse(
        content=[MockBlock("text", text="Done")],
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=10,
    )
    harness = AgentHarness(llm_client=dummy_client, settings={})
    system_tuple = ("Static System Base", "Dynamic Volatile Overlay Notes")
    messages = [{"role": "user", "content": "Analyze EURUSD setup"}]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt=system_tuple,
        messages=messages,
        tools=[],
    )

    assert result["success"] is True
    # Verify effective_sys is static_sys
    called_sys = dummy_client.mock_run_tool_agent.call_args[0][2]
    assert called_sys == "Static System Base"

    # Verify volatile overlay was injected into user message
    sent_msgs = dummy_client.mock_run_tool_agent.call_args[0][0]
    assert "<volatile_overlay>" in sent_msgs[0]["content"]
    assert "Dynamic Volatile Overlay Notes" in sent_msgs[0]["content"]
    assert "Analyze EURUSD setup" in sent_msgs[0]["content"]


@pytest.mark.asyncio
async def test_harness_prompt_cache_hardening_with_tiered_prompt(mock_session, dummy_client):
    from utils.llm.prompt_tiers import TieredSystemPrompt

    dummy_client.provider_name = "anthropic"
    dummy_client.mock_run_tool_agent.return_value = MockResponse(
        content=[MockBlock("text", text="Done")],
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=10,
    )
    harness = AgentHarness(llm_client=dummy_client, settings={})
    tiered = TieredSystemPrompt(
        tier1_stable="Stable Rules",
        tier2_context="Skills Catalog",
        tier3_volatile="Volatile Snapshot",
    )

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt=tiered,
        messages=[{"role": "user", "content": "Start"}],
        tools=[],
    )

    assert result["success"] is True
    # For anthropic, assemble returns structured list of cache blocks
    called_sys = dummy_client.mock_run_tool_agent.call_args[0][2]
    assert isinstance(called_sys, list)
    assert len(called_sys) == 3
    assert called_sys[0]["text"] == "Stable Rules"
    assert called_sys[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_harness_prompt_cache_hardening_with_plain_string(mock_session, dummy_client):
    dummy_client.mock_run_tool_agent.return_value = MockResponse(
        content=[MockBlock("text", text="Done")],
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=10,
    )
    harness = AgentHarness(llm_client=dummy_client, settings={})

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="Simple plain prompt",
        messages=[{"role": "user", "content": "Execute"}],
        tools=[],
    )

    assert result["success"] is True
    called_sys = dummy_client.mock_run_tool_agent.call_args[0][2]
    assert called_sys == "Simple plain prompt"

