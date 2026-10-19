# ==============================================================================
# File: tests/providers/test_tool_schema_normalizer.py
# ==============================================================================

import pytest
from monika.infrastructure.providers.schema_normalizer import (
    CanonicalToolSchema,
    ToolSchemaNormalizer,
)


def test_normalize_openai_format():
    openai_tool = {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Fetch OHLCV price bars",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["symbol"],
            },
        },
    }

    canonical = ToolSchemaNormalizer.normalize_tool(openai_tool)
    assert canonical is not None
    assert canonical.name == "get_price_history"
    assert canonical.description == "Fetch OHLCV price bars"
    assert "symbol" in canonical.parameters["properties"]

    # Convert to Gemini
    gemini_out = ToolSchemaNormalizer.to_gemini([openai_tool])
    assert len(gemini_out) == 1
    assert "functionDeclarations" in gemini_out[0]
    decl = gemini_out[0]["functionDeclarations"][0]
    assert decl["name"] == "get_price_history"
    assert "parameters" in decl

    # Convert to Anthropic
    anthropic_out = ToolSchemaNormalizer.to_anthropic([openai_tool])
    assert len(anthropic_out) == 1
    assert anthropic_out[0]["name"] == "get_price_history"
    assert "input_schema" in anthropic_out[0]


def test_normalize_anthropic_format():
    anthropic_tool = {
        "name": "calculate_rsi",
        "description": "Calculate RSI indicator",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "integer", "default": 14},
            },
        },
    }

    canonical = ToolSchemaNormalizer.normalize_tool(anthropic_tool)
    assert canonical is not None
    assert canonical.name == "calculate_rsi"

    # Convert to OpenAI
    openai_out = ToolSchemaNormalizer.to_openai([anthropic_tool], supports_cache_control=True)
    assert len(openai_out) == 1
    assert openai_out[0]["type"] == "function"
    assert openai_out[0]["function"]["name"] == "calculate_rsi"
    assert openai_out[0]["cache_control"] == {"type": "ephemeral"}


def test_normalize_gemini_format():
    gemini_tool = {
        "name": "get_account_balance",
        "description": "Retrieve balance and equity",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    }

    canonical = ToolSchemaNormalizer.normalize_tool(gemini_tool)
    assert canonical is not None
    assert canonical.name == "get_account_balance"

    # Cross convert to OpenAI and Anthropic
    oai = ToolSchemaNormalizer.to_openai([gemini_tool])
    assert oai[0]["function"]["name"] == "get_account_balance"

    anth = ToolSchemaNormalizer.to_anthropic([gemini_tool])
    assert anth[0]["name"] == "get_account_balance"


def test_normalize_malformed_and_empty():
    assert ToolSchemaNormalizer.normalize_tool(None) is None
    assert ToolSchemaNormalizer.normalize_tool("not a dict") is None
    assert ToolSchemaNormalizer.normalize_tool({}) is None
    assert ToolSchemaNormalizer.normalize_tool({"name": ""}) is None
    assert ToolSchemaNormalizer.normalize_tools([]) == []
