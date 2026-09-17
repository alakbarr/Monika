import pytest
from analysis.providers.capabilities import (
    ModelCapabilities,
    MODEL_CAPABILITIES,
    get_model_capabilities,
    DEFAULT_CAPABILITIES,
)


def test_capabilities_lookup_exact():
    caps = get_model_capabilities("claude-3-5-sonnet")
    assert caps.supports_caching is True
    assert caps.supports_structured_output is True
    assert caps.supports_native_thinking is True
    assert caps.max_output_tokens == 8192


def test_capabilities_lookup_partial():
    # Suffix or variant
    caps = get_model_capabilities("gemini-2.5-flash-preview")
    assert caps.supports_caching is True
    assert caps.supports_structured_output is True

    # Deepseek reasoner
    caps_ds = get_model_capabilities("deepseek-reasoner-v3")
    assert caps_ds.supports_tool_choice is False
    assert caps_ds.requires_reasoning_roundtrip is True


def test_capabilities_unknown_fallback():
    caps_unknown = get_model_capabilities("custom-local-model-xyz")
    assert caps_unknown == DEFAULT_CAPABILITIES

    caps_none = get_model_capabilities(None)
    assert caps_none == DEFAULT_CAPABILITIES
