"""
Unit tests for Forked Subagent Cache Sharing, Turn Prefix Extraction, and GEPALiteEvolver Evaluation.
Covers:
- extract_completed_turn_prefix complete turn boundary extraction
- In-flight turn truncation on unanswered tool calls
- IsolatedSubagentRunner tool array invariance and parent context prefix forking
- Subagent recursion guard fail-closed behavior
- SystemTools delegation depth check
- GEPALiteEvolver evaluator_fn scoring
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from monika.application.analysis.subagent.isolated_harness import (
    MAX_SUBAGENT_DEPTH,
    IsolatedSubagentRunner,
    _subagent_depth,
    extract_completed_turn_prefix,
)
from monika.application.benchmark.prompt_evolution import GEPALiteEvolver
from monika.infrastructure.providers.base_provider import BaseLLMClient, MockBlock, MockResponse


class MockHarnessClient(BaseLLMClient):
    def __init__(self, **kwargs):
        super().__init__(model="test-harness-model", max_tokens=4096, **kwargs)
        self.mock_run = AsyncMock()

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "text"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None, max_tokens=None):
        return {}

    async def run_tool_agent(self, messages: list, tools: list, system_prompt=None):
        return await self.mock_run(messages, tools, system_prompt)

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {"reply": "ok"}


def test_extract_completed_turn_prefix_all_answered():
    """Prefix extraction preserves all messages when every tool call is answered."""
    messages = [
        {"role": "user", "content": "Start query"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "get_quote", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "100.0"},
            ],
        },
        {"role": "assistant", "content": "Analysis completed."},
    ]

    prefix = extract_completed_turn_prefix(messages)
    assert len(prefix) == 4
    assert prefix[-1]["content"] == "Analysis completed."


def test_extract_completed_turn_prefix_truncates_incomplete_turn():
    """Prefix extraction drops incomplete in-flight turn with pending tool calls."""
    messages = [
        {"role": "user", "content": "Start query"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "get_quote", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "100.0"},
            ],
        },
        # In-flight incomplete turn: t2 was never answered
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t2", "name": "get_atr", "input": {}},
            ],
        },
    ]

    prefix = extract_completed_turn_prefix(messages)
    # The last turn (index 3) is incomplete and must be truncated
    assert len(prefix) == 3
    assert prefix[-1]["content"][0]["tool_use_id"] == "t1"


@pytest.mark.asyncio
async def test_forked_subagent_preserves_tools_and_prepends_cache_prefix():
    """Forking parent context preserves tool schema array exactly and shares KV prefix."""
    client = MockHarnessClient()
    runner = IsolatedSubagentRunner()

    captured_call = {}

    async def capture_run(messages, tools, system_prompt, **kwargs):
        captured_call["messages"] = messages
        captured_call["tools"] = tools
        captured_call["system_prompt"] = system_prompt
        return MockResponse(
            content=[MockBlock("text", text="Subagent specialized findings.")],
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
        )

    client.mock_run.side_effect = capture_run

    parent_history = [
        {"role": "user", "content": "Initial parent query"},
        {"role": "assistant", "content": "Parent preliminary analysis"},
    ]

    tool_definitions = [
        {"name": "delegate_specialist_analysis", "description": "Delegate subtask"},
        {"name": "get_quote", "description": "Get market quote"},
    ]

    result = await runner.run_isolated(
        role_name="technical_specialist",
        llm_client=client,
        system_prompt="System prompt for analyst",
        messages=[{"role": "user", "content": "Deep dive into SMC order blocks"}],
        tools=tool_definitions,
        fork_parent_context=True,
        parent_messages=parent_history,
        keep_tool_schema_invariant=True,
    )

    assert result["success"] is True
    # 1. Tool schema invariance: delegate_specialist_analysis is NOT stripped!
    tool_names = [t["name"] for t in captured_call["tools"]]
    assert "delegate_specialist_analysis" in tool_names
    assert "get_quote" in tool_names
    assert len(tool_names) == 2

    # 2. KV Cache Prefix: parent history is prepended, tail message wraps delegation
    dispatched_msgs = captured_call["messages"]
    assert len(dispatched_msgs) == 3
    assert dispatched_msgs[0]["content"] == "Initial parent query"
    assert dispatched_msgs[1]["content"] == "Parent preliminary analysis"
    assert "<subagent_delegation>" in dispatched_msgs[2]["content"]
    assert "Role: technical_specialist" in dispatched_msgs[2]["content"]
    assert "Deep dive into SMC order blocks" in dispatched_msgs[2]["content"]


@pytest.mark.asyncio
async def test_subagent_recursion_guard_fails_closed():
    """IsolatedSubagentRunner rejects delegation when depth exceeds MAX_SUBAGENT_DEPTH."""
    client = MockHarnessClient()
    runner = IsolatedSubagentRunner()

    token = _subagent_depth.set(MAX_SUBAGENT_DEPTH)
    try:
        result = await runner.run_isolated(
            role_name="nested_subagent",
            llm_client=client,
            system_prompt="Nested",
            messages=[{"role": "user", "content": "Run"}],
            tools=[],
        )
        assert result["success"] is False
        assert f"Maximum subagent delegation depth ({MAX_SUBAGENT_DEPTH}) reached" in result["error"]
    finally:
        _subagent_depth.reset(token)


@pytest.mark.asyncio
async def test_gepa_lite_evolver_uses_evaluator_fn():
    """GEPALiteEvolver computes score using evaluator_fn when provided."""
    mock_client = AsyncMock()
    mock_client.generate.return_value = (
        "Optimized mutated trading prompt variant with complete safety invariants.\n"
        "Preserves mathematical constraints, strict risk limits, and compact formatting."
    )

    with patch("monika.infrastructure.providers.llm_factory.get_client_for_task", return_value=mock_client):
        evolver = GEPALiteEvolver()

        def custom_oracle_evaluator(prompt: str, scenarios: list) -> float:
            # Domain oracle returning high score for complete variants
            return 9.5

        result = await evolver.evolve_round(
            population_size=1,
            generations=1,
            evaluator_fn=custom_oracle_evaluator,
            scenarios=[{"market": "bull"}],
        )

        assert "prompt" in result
        assert "score" in result
        # Evaluated score should reflect weighted evaluation: 0.7 * 9.5 + 0.3 * compression_score >= 8.5
        assert result["score"] >= 8.5
