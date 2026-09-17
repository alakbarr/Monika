import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from analysis.providers.structured_fallback import (
    extract_key_values_by_regex,
    parse_structured_output,
    invoke_structured_or_freetext,
    StructuredOutputResult,
)


class DummyDecisionModel(BaseModel):
    decision: str
    confidence: float


def test_extract_key_values_by_regex():
    text = (
        "Based on my analysis, the decision is 'BUY'. "
        "The market is moving strongly and confidence is 0.85. "
        "Also confirmed is true and tags: ['forex', 'breakout']."
    )
    extracted = extract_key_values_by_regex(text, ["decision", "confidence", "confirmed", "tags"])
    assert extracted["decision"] == "BUY"
    assert extracted["confidence"] == 0.85
    assert extracted["confirmed"] is True
    assert extracted["tags"] == ["forex", "breakout"]


def test_parse_structured_output_native():
    raw_json = '{"decision": "BUY", "confidence": 0.95}'
    res = parse_structured_output(raw_json, pydantic_model=DummyDecisionModel)
    assert res.success is True
    assert res.degradation_stage == "native"
    assert res.data["decision"] == "BUY"
    assert res.data["confidence"] == 0.95
    assert isinstance(res.model_instance, DummyDecisionModel)


def test_parse_structured_output_repaired_json():
    # Markdown fence + trailing comma
    broken_json = '```json\n{"decision": "SELL", "confidence": 0.70,}\n```'
    res = parse_structured_output(broken_json, pydantic_model=DummyDecisionModel)
    assert res.success is True
    assert res.degradation_stage == "repaired_json"
    assert res.data["decision"] == "SELL"
    assert res.data["confidence"] == 0.70


def test_parse_structured_output_regex_recovery():
    # Model returns rambling unstructured text
    messy_text = (
        "Here is what I found. Overall bias is negative so my decision: 'SELL'. "
        "My calculated confidence is 0.65. Target is 1.0800."
    )
    res = parse_structured_output(
        messy_text,
        pydantic_model=DummyDecisionModel,
        required_fields=["decision", "confidence"],
    )
    assert res.success is True
    assert res.degradation_stage == "regex_field_recovery"
    assert res.data["decision"] == "SELL"
    assert res.data["confidence"] == 0.65
    assert isinstance(res.model_instance, DummyDecisionModel)


def test_parse_structured_output_default_fallback():
    # Completely empty or garbage text
    garbage = "I don't know what to say. The market is closed. Goodbye."
    defaults = {"decision": "WAIT", "confidence": 0.0}
    res = parse_structured_output(
        garbage,
        pydantic_model=DummyDecisionModel,
        defaults=defaults,
    )
    assert res.success is False
    assert res.degradation_stage == "default_fallback"
    assert res.data["decision"] == "WAIT"
    assert res.data["confidence"] == 0.0


@pytest.mark.asyncio
async def test_invoke_structured_or_freetext_with_recovery():
    client = MagicMock()
    # classify_json throws error
    client.classify_json = AsyncMock(side_effect=RuntimeError("Provider API error"))
    # generate returns messy text
    client.generate = AsyncMock(return_value="My output is decision: 'BUY' with confidence: 0.92")

    res = await invoke_structured_or_freetext(
        client=client,
        prompt="Analyze EURUSD",
        system_prompt="Return decision",
        pydantic_model=DummyDecisionModel,
        required_fields=["decision", "confidence"],
        defaults={"decision": "WAIT", "confidence": 0.0},
    )
    assert res["decision"] == "BUY"
    assert res["confidence"] == 0.92
