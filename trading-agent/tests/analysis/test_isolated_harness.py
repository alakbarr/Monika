"""
Unit tests for Isolated Subagent Harness (H3).
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from analysis.subagent.isolated_harness import IsolatedSubagentRunner
from analysis.providers.base_provider import BaseLLMClient, MockResponse, MockBlock


class DummySubagentClient(BaseLLMClient):
    def __init__(self, **kwargs):
        super().__init__(model="dummy-model", max_tokens=4096, **kwargs)
        self.mock_run = AsyncMock()

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "text"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None, max_tokens=None):
        return {}

    async def run_tool_agent(self, messages: list, tools: list, system_prompt=None):
        return await self.mock_run(messages, tools, system_prompt)

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {"reply": "ok"}


@pytest.mark.asyncio
async def test_h3_subagent_successful_isolation():
    """H3: Subagent executes in isolated harness and returns structured result."""
    client = DummySubagentClient()
    runner = IsolatedSubagentRunner()

    resp = MockResponse(
        content=[MockBlock("text", text="Specialist report: Bullish momentum detected.")],
        stop_reason="end_turn",
        input_tokens=120,
        output_tokens=40,
    )
    client.mock_run.return_value = resp

    parent_messages = [{"role": "user", "content": "Analyze technical indicators"}]
    result = await runner.run_isolated(
        role_name="technical_analyst",
        llm_client=client,
        system_prompt="You are a technical analyst specialist.",
        messages=parent_messages,
        tools=[],
        timeout=10,
    )

    assert result["success"] is True
    assert "Bullish momentum" in result["final_text"]
    # Ensure parent messages was not mutated
    assert len(parent_messages) == 1


@pytest.mark.asyncio
async def test_h3_subagent_timeout_watchdog():
    """H3: Subagent exceeding timeout budget gets safely cancelled and flagged."""
    client = DummySubagentClient()
    runner = IsolatedSubagentRunner()

    async def slow_execution(messages, tools, system_prompt, **kwargs):
        await asyncio.sleep(5.0)
        return MockResponse(content=[MockBlock("text", text="Late")], stop_reason="end_turn")

    client.mock_run.side_effect = slow_execution

    result = await runner.run_isolated(
        role_name="slow_specialist",
        llm_client=client,
        system_prompt="Specialist",
        messages=[{"role": "user", "content": "Start"}],
        tools=[],
        timeout=1,  # 1 second timeout
    )

    assert result["success"] is False
    assert "timed out" in result["error"].lower()

