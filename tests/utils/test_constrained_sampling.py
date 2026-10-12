import pytest
from utils.llm.constrained_sampling import (
    ConstrainedSamplingConfig,
    make_strict_json_schema,
    resolve_grammar_for_provider,
)
from analysis.providers.base_provider import BaseLLMClient


class ConcreteClient(BaseLLMClient):
    async def generate(self, *args, **kwargs): pass
    async def classify_json(self, *args, **kwargs): pass
    async def run_chat_loop(self, *args, **kwargs): pass
    async def run_tool_agent(self, *args, **kwargs): pass


def test_make_strict_json_schema():
    schema = {
        "type": "object",
        "properties": {
            "signal": {"type": "string"},
            "confidence": {"type": "number"},
            "levels": {
                "type": "object",
                "properties": {
                    "entry": {"type": "number"},
                    "stop_loss": {"type": "number"},
                },
            },
        },
    }

    strict = make_strict_json_schema(schema)

    assert strict["additionalProperties"] is False
    assert set(strict["required"]) == {"signal", "confidence", "levels"}
    assert strict["properties"]["levels"]["additionalProperties"] is False
    assert set(strict["properties"]["levels"]["required"]) == {"entry", "stop_loss"}


def test_resolve_grammar_ollama():
    config = ConstrainedSamplingConfig(json_schema={"type": "object", "properties": {"a": {"type": "string"}}})
    params = resolve_grammar_for_provider(config, "ollama")
    assert params is not None
    assert "format" in params
    assert params["format"]["additionalProperties"] is False


def test_resolve_grammar_openai():
    config = ConstrainedSamplingConfig(json_schema={"type": "object", "properties": {"a": {"type": "string"}}})
    params = resolve_grammar_for_provider(config, "openai")
    assert params is not None
    assert params["response_format"]["type"] == "json_schema"
    assert params["response_format"]["json_schema"]["strict"] is True


def test_resolve_grammar_gemini():
    config = ConstrainedSamplingConfig(json_schema={"type": "object", "properties": {"a": {"type": "string"}}})
    params = resolve_grammar_for_provider(config, "gemini")
    assert params is not None
    assert params["responseMimeType"] == "application/json"
    assert "responseSchema" in params


def test_preserve_reasoning_signatures():
    client = ConcreteClient(model="test-model", settings=None)
    messages = [
        {"role": "user", "content": "Analyze USDJPY"},
        {
            "role": "assistant",
            "content": [
                {"type": "redacted_thinking", "data": "opaque_hash_123"},
                {"type": "text", "text": "Signal is BUY", "thoughtSignature": "gemini_sig_456"},
            ],
        },
    ]

    # Replaying against Anthropic preserves redacted_thinking
    anthropic_msgs = client._preserve_reasoning_signatures(messages, "anthropic")
    anth_types = [b.get("type") for b in anthropic_msgs[1]["content"]]
    assert "redacted_thinking" in anth_types

    # Replaying against OpenAI strips redacted_thinking and thoughtSignature
    openai_msgs = client._preserve_reasoning_signatures(messages, "openai")
    openai_types = [b.get("type") for b in openai_msgs[1]["content"]]
    assert "redacted_thinking" not in openai_types
    assert "thoughtSignature" not in openai_msgs[1]["content"][0]
