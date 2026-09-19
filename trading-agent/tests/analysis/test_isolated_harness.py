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


@pytest.mark.asyncio
async def test_h3_subagent_output_schema_validation_success():
    """Subagent returns valid JSON adhering to output_schema."""
    client = DummySubagentClient()
    runner = IsolatedSubagentRunner()

    schema = {
        "type": "object",
        "properties": {
            "bias": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
            "confidence": {"type": "number"},
        },
        "required": ["bias", "confidence"],
    }

    client.mock_run.return_value = MockResponse(
        content=[MockBlock("text", text='```json\n{"bias": "bullish", "confidence": 0.85}\n```')],
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=30,
    )

    result = await runner.run_isolated(
        role_name="sentiment_analyst",
        llm_client=client,
        system_prompt="Analyze sentiment",
        messages=[{"role": "user", "content": "Analyze EURUSD sentiment"}],
        tools=[],
        output_schema=schema,
    )

    assert result["success"] is True
    assert result.get("schema_valid") is True
    assert result["parsed_output"] == {"bias": "bullish", "confidence": 0.85}


@pytest.mark.asyncio
async def test_h3_subagent_output_schema_auto_correction():
    """Subagent receives 1-turn auto-correction nudge when first output violates schema."""
    client = DummySubagentClient()
    runner = IsolatedSubagentRunner()

    schema = {
        "type": "object",
        "properties": {
            "bias": {"type": "string"},
            "level": {"type": "number"},
        },
        "required": ["bias", "level"],
    }

    # Turn 1: Plain text without required JSON schema
    turn1_resp = MockResponse(
        content=[MockBlock("text", text="I think it's bullish around 1.0850")],
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=30,
    )
    # Turn 2: Corrected JSON response following nudge
    turn2_resp = MockResponse(
        content=[MockBlock("text", text='{"bias": "bullish", "level": 1.0850}')],
        stop_reason="end_turn",
        input_tokens=150,
        output_tokens=40,
    )

    client.mock_run.side_effect = [turn1_resp, turn2_resp]

    result = await runner.run_isolated(
        role_name="technical_analyst",
        llm_client=client,
        system_prompt="Analyze level",
        messages=[{"role": "user", "content": "Analyze key level"}],
        tools=[],
        output_schema=schema,
    )

    assert result["success"] is True
    assert result.get("schema_valid") is True
    assert result["parsed_output"]["bias"] == "bullish"
    assert result["parsed_output"]["level"] == 1.0850

