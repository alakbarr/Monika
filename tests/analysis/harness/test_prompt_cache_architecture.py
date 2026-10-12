import pytest
from unittest.mock import MagicMock
from analysis.harness.agent_harness import AgentHarness
from analysis.providers.openai_provider import _canonicalize_schema
from analysis.providers.base_provider import BaseLLMClient


class DummyProvider(BaseLLMClient):
    def __init__(self, model="deepseek-chat", provider_name="deepseek"):
        super().__init__(model=model)
        self.provider_name = provider_name
        self.recorded_calls = []

    async def run_tool_agent(self, messages, tools, system_prompt):
        self.recorded_calls.append({
            "messages": [dict(m) for m in messages],
            "tools": list(tools) if tools else [],
            "system_prompt": system_prompt,
        })
        from analysis.providers.base_provider import MockResponse, MockBlock
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
    raw_schema = {
        "z_prop": {"b_sub": 2, "a_sub": 1},
        "a_prop": [
            {"d": 4, "c": 3},
            {"b": 2, "a": 1}
        ]
    }
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

    initial_messages = [
        {"role": "user", "content": "Analyze USDJPY liquidity"}
    ]

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

