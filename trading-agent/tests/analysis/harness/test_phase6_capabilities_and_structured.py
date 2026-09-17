"""Unit tests for model capabilities and structured output fallback (Phase 6)."""

import pytest
from pydantic import BaseModel, Field
from unittest.mock import AsyncMock, MagicMock

from utils.llm.model_capabilities import ModelCapabilities, get_capabilities
from analysis.harness.structured_output import invoke_structured_or_freetext


class SampleDecision(BaseModel):
    bias: str = Field(description="Market bias")
    confidence: float = Field(description="Confidence score 0 to 1")


def test_model_capabilities_lookup():
    claude_caps = get_capabilities("claude-3-5-sonnet-20241022")
    assert claude_caps.prompt_cache_strategy == "anthropic_system_and_3"
    assert claude_caps.context_window == 200000

    gemini_caps = get_capabilities("gemini-2.5-flash")
    assert gemini_caps.prompt_cache_strategy == "gemini_context"
    assert gemini_caps.supports_tool_choice is True

    deepseek_caps = get_capabilities("deepseek-reasoner")
    assert deepseek_caps.requires_reasoning_roundtrip is True
    assert deepseek_caps.supports_tool_choice is False

    unknown_caps = get_capabilities("unknown-future-model")
    assert isinstance(unknown_caps, ModelCapabilities)
    assert unknown_caps.prompt_cache_strategy == "none"


@pytest.mark.asyncio
async def test_structured_output_success():
    client = MagicMock()
    mock_decision = SampleDecision(bias="BULLISH", confidence=0.85)
    client.generate_structured = AsyncMock(return_value=mock_decision)

    def render(d: SampleDecision) -> str:
        return f"DECISION: {d.bias} ({d.confidence})"

    rendered = await invoke_structured_or_freetext(
        llm_client=client,
        prompt="Analyze EURUSD",
        schema=SampleDecision,
        render_fn=render,
    )
    assert rendered == "DECISION: BULLISH (0.85)"
    client.generate_structured.assert_called_once()


@pytest.mark.asyncio
async def test_structured_output_fallback_to_freetext():
    client = MagicMock()
    client.generate_structured = AsyncMock(side_effect=RuntimeError("Structured output decode error"))
    client.generate = AsyncMock(return_value=MagicMock(content="Free text fallback analysis: Neutral."))

    def render(d: SampleDecision) -> str:
        return f"DECISION: {d.bias} ({d.confidence})"

    rendered = await invoke_structured_or_freetext(
        llm_client=client,
        prompt="Analyze GBPUSD",
        schema=SampleDecision,
        render_fn=render,
    )
    assert rendered == "Free text fallback analysis: Neutral."
    client.generate.assert_called_once()


@pytest.mark.asyncio
async def test_structured_output_fallback_dict_response():
    """Verify structured output fallback extracts content cleanly when client returns a dict."""
    client = MagicMock()
    client.generate_structured = AsyncMock(side_effect=RuntimeError("Structured output decode error"))
    client.generate = AsyncMock(return_value={"content": "Free text from dict payload"})

    rendered = await invoke_structured_or_freetext(
        llm_client=client,
        prompt="Analyze USDJPY",
        schema=SampleDecision,
        render_fn=lambda d: str(d),
    )
    assert rendered == "Free text from dict payload"

