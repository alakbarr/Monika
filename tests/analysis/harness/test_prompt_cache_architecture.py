import pytest
from unittest.mock import MagicMock
from monika.application.analysis.harness.agent_harness import AgentHarness
from monika.infrastructure.providers.openai_provider import _canonicalize_schema
from monika.infrastructure.providers.base_provider import BaseLLMClient


class DummyProvider(BaseLLMClient):
    def __init__(self, model="deepseek-chat", provider_name="deepseek"):
        super().__init__(model=model)
        self.provider_name = provider_name
        self.recorded_calls = []

    async def run_tool_agent(self, messages, tools, system_prompt):
        self.recorded_calls.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": list(tools) if tools else [],
                "system_prompt": system_prompt,
            }
        )
        from monika.infrastructure.providers.base_provider import MockResponse, MockBlock

        return MockResponse(
            content=[MockBlock("text", text="All analysis done.")],
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=10,
        )

    async def generate(self, *args, **kwargs):
        return "Done"

    async def classify_json(self, *args, **kwargs):
        return {}

    async def run_chat_loop(self, *args, **kwargs):
        return {}


def test_tool_schema_recursive_canonicalization():
    raw_schema = {"z_prop": {"b_sub": 2, "a_sub": 1}, "a_prop": [{"d": 4, "c": 3}, {"b": 2, "a": 1}]}
    canonical = _canonicalize_schema(raw_schema)
    assert list(canonical.keys()) == ["a_prop", "z_prop"]
    assert list(canonical["z_prop"].keys()) == ["a_sub", "b_sub"]
    assert list(canonical["a_prop"][0].keys()) == ["c", "d"]
    assert list(canonical["a_prop"][1].keys()) == ["a", "b"]


def test_deepseek_session_affinity_headers():
    provider = DummyProvider(model="deepseek-chat", provider_name="deepseek")
    headers = provider._get_session_affinity_headers()
    assert "X-Session-ID" in headers
    assert "x-session-id" in headers
    assert headers["X-Session-ID"] == headers["x-session-id"]
    assert len(headers["X-Session-ID"]) == 32


@pytest.mark.asyncio
async def test_surface_node_0_immutability_across_turns():
    client = DummyProvider(model="deepseek-chat", provider_name="deepseek")
    harness = AgentHarness(llm_client=client, max_tool_turns=3)

    system_tuple = ("Static Invariant Identity", "Volatile timestamp 12:00")
    messages = [{"role": "user", "content": "Analyze markets"}]

    await harness.run_agent_from_messages(
        session=None,
        system_prompt=system_tuple,
        messages=messages,
        tools=[],
        max_tool_turns=1,
    )

    assert len(client.recorded_calls) == 1
    call1 = client.recorded_calls[0]
    assert call1["system_prompt"] == "Static Invariant Identity"
    assert any("<volatile_overlay>" in str(m.get("content", "")) for m in call1["messages"])

    await harness.run_agent_from_messages(
        session=None,
        system_prompt=("Updated System Prompt", "Volatile timestamp 12:05"),
        messages=call1["messages"],
        tools=[],
        max_tool_turns=1,
    )
    assert len(client.recorded_calls) == 2
    call2 = client.recorded_calls[1]
    # Surface Node 0 remains immutable at token 0
    assert call2["system_prompt"] == "Static Invariant Identity"
    # System update is appended in-history
    assert any("[SYSTEM INSTRUCTION UPDATE]" in str(m.get("content", "")) for m in call2["messages"])


@pytest.mark.asyncio
async def test_harness_negative_prompt_cache_rollback_on_failure():
    class FailingMockClient:
        model = "gpt-4o"
        provider_name = "openai"

        async def run_tool_agent(self, messages, tools, system_prompt):
            raise RuntimeError("Fatal upstream corruption 500")

    client = FailingMockClient()
    harness = AgentHarness(llm_client=client, settings={})

    initial_messages = [{"role": "user", "content": "Analyze USDJPY liquidity"}]

    res = await harness.run_agent_from_messages(
        session=None,
        system_prompt="System Prompt",
        messages=initial_messages,
        tools=[],
        max_tool_turns=1,
    )

    assert res["success"] is False
    assert "Fatal upstream corruption" in str(res["error"])
    # Input messages passed in initial_messages remain unmodified (clean checkpoint preserved)
    assert len(initial_messages) == 1
    assert initial_messages[0]["content"] == "Analyze USDJPY liquidity"


@pytest.mark.asyncio
async def test_multiturn_react_surface_node_0_byte_invariance():
    """Verify that messages[0] with pre-fetched data remains 100% byte-identical across 5 ReAct turns."""
    import hashlib
    from monika.infrastructure.providers.base_provider import MockResponse, MockBlock

    recorded_turns = []

    class MultiTurnMockClient(BaseLLMClient):
        def __init__(self):
            super().__init__(model="deepseek-chat")
            self.provider_name = "deepseek"

        async def run_tool_agent(self, messages, tools, system_prompt):
            from monika.infrastructure.providers.base_provider import MockBlock, MockResponse

            recorded_turns.append([dict(m) for m in messages])
            turn_no = len(recorded_turns)
            if turn_no < 5:
                # Issue a tool call with unique parameters to continue the loop
                tool_block = MockBlock(
                    "tool_use",
                    id=f"tool_call_{turn_no}",
                    name="get_market_data",
                    input={"symbol": "EURUSD", "timeframe": f"M{turn_no}"},
                )
                return MockResponse(
                    content=[tool_block],
                    stop_reason="tool_use",
                    input_tokens=1000,
                    output_tokens=50,
                )
            # Final turn
            return MockResponse(
                content=[MockBlock("text", text="Analysis finalized.")],
                stop_reason="end_turn",
                input_tokens=1500,
                output_tokens=100,
            )

        async def generate(self, *args, **kwargs):
            return "Done"

        async def classify_json(self, *args, **kwargs):
            return {}

        async def run_chat_loop(self, *args, **kwargs):
            return {}

    client = MultiTurnMockClient()
    harness = AgentHarness(llm_client=client, max_tool_turns=5)

    initial_content = (
        "Analyze EURUSD orderflow.\n\n[PRE-FETCHED DATA]\n"
        + ("candle_row_sample_data_point_close_1.0850\n" * 50)
        + "regime: trending_bullish\natr: 0.0065"
    )
    initial_sha = hashlib.sha256(initial_content.encode("utf-8")).hexdigest()

    mock_tool = {
        "name": "get_market_data",
        "description": "Fetch market data",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
    }

    class MockExecutor:
        async def execute(self, name, args):
            return {"status": "ok", "price": 1.0855, "volume": 1200}

    res = await harness.run_agent(
        session=None,
        system_prompt=("System Strategy Invariant", "Volatile clock 10:00"),
        user_message=initial_content,
        tools=[mock_tool],
        tool_executor=MockExecutor(),
        max_tool_turns=5,
    )

    assert res["success"] is True
    assert len(recorded_turns) >= 5

    # Check Surface Node 0 invariant across every recorded LLM turn
    for i, turn_msgs in enumerate(recorded_turns):
        first_msg = turn_msgs[0]
        assert first_msg["role"] == "user"
        content = first_msg["content"]
        # Verify content starts with exact initial content
        assert content.startswith(initial_content)
        # Verify prefetch distillation did not destroy raw prefetch bundle
        assert "[PRE-FETCHED DATA DISTILLED]" not in content
        assert "candle_row_sample_data_point_close_1.0850" in content

    # Verify that turn 2..5 messages[0] is byte-for-byte identical to turn 1 messages[0]
    turn1_msg0_sha = hashlib.sha256(str(recorded_turns[0][0]["content"]).encode("utf-8")).hexdigest()
    for i in range(1, len(recorded_turns)):
        current_sha = hashlib.sha256(str(recorded_turns[i][0]["content"]).encode("utf-8")).hexdigest()
        assert current_sha == turn1_msg0_sha, f"Turn {i + 1} mutated messages[0]! Surface Node 0 broken."


@pytest.mark.asyncio
async def test_openai_provider_openrouter_claude_4_breakpoints():
    """Verify that OpenAIProvider sets up to 4 cache_control breakpoints on OpenRouter for Claude."""
    from unittest.mock import AsyncMock
    from monika.infrastructure.providers.openai_provider import OpenAIProvider

    captured_kwargs = {}

    provider = OpenAIProvider(
        model="anthropic/claude-3.5-sonnet",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        provider_name="openrouter",
    )

    class MockClient:
        base_url = "https://openrouter.ai/api/v1"

    provider.client = MockClient()

    async def mock_create(kwargs):
        captured_kwargs.update(kwargs)
        from monika.infrastructure.providers.base_provider import MockResponse, MockBlock

        return MockResponse(
            content=[MockBlock("text", text="ok")],
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=10,
        )

    provider._create_chat_completion = mock_create

    tools = [
        {"name": "fetch_news", "description": "Fetch news", "parameters": {"type": "object", "properties": {}}},
        {"name": "calc_lot", "description": "Calc lots", "parameters": {"type": "object", "properties": {}}},
    ]

    messages = [
        {"role": "user", "content": "Initial trade query"},
        {
            "role": "assistant",
            "content": "I will check news",
            "tool_calls": [{"id": "call_1", "function": {"name": "fetch_news", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "No major news"},
        {
            "role": "assistant",
            "content": "Now checking size",
            "tool_calls": [{"id": "call_2", "function": {"name": "calc_lot", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_2", "content": "Lot: 0.5"},
    ]

    await provider.run_tool_agent(messages=messages, tools=tools, system_prompt="System Directive")

    req_messages = captured_kwargs["messages"]
    req_tools = captured_kwargs["tools"]

    # 1. System prompt has cache_control
    sys_msg = req_messages[0]
    assert sys_msg["role"] == "system"
    assert sys_msg["content"][0]["cache_control"] == {"type": "ephemeral"}

    # 2. Last tool has cache_control
    assert "cache_control" not in req_tools[0]
    assert req_tools[1]["cache_control"] == {"type": "ephemeral"}

    # 3. Message turns have cache_control at completed endpoints
    msg_cache_count = 0
    for m in req_messages[1:]:
        c = m.get("content")
        if isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and "cache_control" in part:
                    msg_cache_count += 1

    assert msg_cache_count >= 1
    # Total breakpoints across system (1) + tools (1) + messages (<=2) <= 4
    total_breakpoints = 1 + 1 + msg_cache_count
    assert total_breakpoints <= 4


@pytest.mark.asyncio
async def test_news_classification_system_prompt_elevation_and_prefix_invariance():
    """Verify that NewsClassificationMixin pads system prompt above 4,096 tokens (>=16,500 chars)
    and isolates volatile timestamps & news items strictly at the prompt tail.
    """
    from datetime import datetime, timezone, timedelta
    from unittest.mock import AsyncMock, MagicMock
    from monika.application.analysis.prefetch.news_digest.processor import NewsDigestProcessor
    from monika.infrastructure.database.models import NewsItem

    captured_calls = []

    class MockClassifier(DummyProvider):
        def __init__(self):
            super().__init__(model="gemini-2.5-flash", provider_name="gemini")

        async def classify_json(self, prompt, system_prompt=None, schema=None, **kwargs):
            captured_calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return [
                {
                    "index": 1,
                    "news_id": 100 + len(captured_calls),
                    "impact": "HIGH",
                    "confidence": 0.9,
                    "currencies": ["USD"],
                    "sentiments": ["BULLISH_USD"],
                }
            ]

    mock_client = MockClassifier()
    processor = NewsDigestProcessor(settings={"news_classification": {"batch_size": 1}})
    processor._classifier = mock_client
    processor._flash_lite = mock_client

    now_base = datetime.now(timezone.utc)
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    items = []
    for i in range(5):
        item = NewsItem(
            id=101 + i,
            title=f"Unique Headline {i}: US Treasury yields jump {10 + i} bps",
            summary=f"Summary for item {i}",
            fetched_at=now_base - timedelta(minutes=5 * (i + 1)),
            published_at=now_base - timedelta(minutes=10 * (i + 1)),
            impact=None,
        )
        items.append(item)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    exec_res_mock = MagicMock()
    exec_res_mock.scalars.return_value = scalars_mock
    exec_res_mock.scalar_one_or_none.return_value = 0
    mock_session.execute.return_value = exec_res_mock

    # Mock helper methods to avoid DB hits during test
    processor._get_recent_classified_titles = AsyncMock(return_value=[])
    processor._build_5day_macro_context = AsyncMock(return_value="[5D Macro Regime: Moderate Risk-Off]")
    processor._get_calendar_impact_priors = AsyncMock(return_value={})
    processor._validate_classification_batch = AsyncMock(side_effect=lambda s, res, b, n, sb, g, c: res)

    await processor.classify_unscored_news(mock_session, hours_back=6)

    assert len(captured_calls) == 5

    # 1. System prompt length >= 16,500 chars (~4,125 tokens) for Gemini 4,096 threshold
    for call in captured_calls:
        sys_p = call["system_prompt"]
        assert sys_p is not None
        assert len(sys_p) >= 16500, f"Expected system prompt >= 16500 chars, got {len(sys_p)}"
        assert "=== MONIKA FINANCIAL TAXONOMY & NEWS IMPACT CLASSIFICATION ONTOLOGY ===" in sys_p

    # 2. Characters 0..4000 of system prompt are 100% byte-identical across all 5 requests
    base_sys_prefix = captured_calls[0]["system_prompt"][:4000]
    for i in range(1, 5):
        assert captured_calls[i]["system_prompt"][:4000] == base_sys_prefix

    # 3. User prompt isolates volatile <runtime_item> at the tail
    for call in captured_calls:
        prompt = call["prompt"]
        assert "<runtime_item current_time=" in prompt
        assert prompt.endswith("</runtime_item>")


@pytest.mark.asyncio
async def test_news_digest_macro_overview_and_currency_elevation():
    """Verify that create_news_digest pads system prompts and isolates headlines at tail."""
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock
    from monika.application.analysis.prefetch.news_digest.processor import NewsDigestProcessor
    from monika.infrastructure.database.models import NewsItem

    captured_gen_calls = []

    class MockSynthClient(DummyProvider):
        def __init__(self):
            super().__init__(model="gemini-2.5-flash", provider_name="gemini")

        async def generate(self, prompt, system=None, **kwargs):
            captured_gen_calls.append({"prompt": prompt, "system": system})
            return "Valid synthesized text for macro overview or currency."

    mock_client = MockSynthClient()
    processor = NewsDigestProcessor(settings={})
    processor._macro_synth = mock_client
    processor._digest_generator = mock_client
    processor._verifier = mock_client

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    processor._should_use_cache = AsyncMock(return_value=(False, None))
    processor._cleanup_old_digests = AsyncMock()
    processor._build_structured_metadata = AsyncMock(return_value="[Metadata]")
    processor._build_structured_metadata_dict = AsyncMock(return_value={})
    processor._build_currency_signals_summary = AsyncMock(return_value="[Signals]")
    processor._build_5day_macro_context = AsyncMock(return_value="[5D Macro]")
    processor._extract_prior_metadata = MagicMock(return_value={})
    processor._build_structured_delta = MagicMock(return_value="[Delta]")

    item = NewsItem(
        id=201,
        title="Fed signals rate pause as core PCE cools to 2.4%",
        summary="Federal Reserve policymakers expressed confidence in disinflation path.",
        impact="BREAKING",
        currency_tags="USD",
        fetched_at=datetime.now(timezone.utc),
    )

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [item]
    exec_res_mock = MagicMock()
    exec_res_mock.scalars.return_value = scalars_mock
    exec_res_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = exec_res_mock

    await processor.create_news_digest(mock_session, hours_back=12)

    assert len(captured_gen_calls) >= 1
    macro_call = captured_gen_calls[0]
    # Macro overview system prompt padded >= 16500 chars
    assert len(macro_call["system"]) >= 16500
    assert "=== MONIKA SENIOR MACRO ANALYSIS & SYNTHESIS DIRECTIVE ===" in macro_call["system"]
    # News text is isolated at the tail
    assert macro_call["prompt"].endswith("</runtime_news_data>")
