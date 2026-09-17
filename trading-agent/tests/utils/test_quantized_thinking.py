import pytest
from utils.llm.adaptive_thinking import QuantizedThinkingAllocator, PerSymbolAdaptiveThinkingAllocator
from analysis.providers.anthropic_provider import AnthropicProvider
from analysis.providers.gemini_provider import GeminiProvider
from analysis.providers.openai_provider import OpenAIProvider

def test_quantized_thinking_allocator_buckets():
    assert QuantizedThinkingAllocator.quantize(500) == 1024
    assert QuantizedThinkingAllocator.quantize(1024) == 1024
    assert QuantizedThinkingAllocator.quantize(2400) == 1024
    assert QuantizedThinkingAllocator.quantize(2500) == 4096
    assert QuantizedThinkingAllocator.quantize(4000) == 4096
    assert QuantizedThinkingAllocator.quantize(6999) == 4096
    assert QuantizedThinkingAllocator.quantize(7000) == 10000
    assert QuantizedThinkingAllocator.quantize(10000) == 10000
    assert QuantizedThinkingAllocator.quantize(12999) == 10000
    assert QuantizedThinkingAllocator.quantize(13000) == 16000
    assert QuantizedThinkingAllocator.quantize(16384) == 16000

def test_per_symbol_adaptive_thinking_quantized_default():
    # Test EURUSD low volatility
    eur_budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
        "EURUSD", context={"vix": 15.0, "confluence_score": 9.0}, base_budget=4000, quantized=True
    )
    assert eur_budget in (1024, 4096, 10000, 16000)

    # Test BTCUSD crisis regime
    btc_budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
        "BTCUSD", context={"vix": 35.0, "confluence_score": 6.5, "regime": "CRISIS_SHIFT"}, base_budget=4000, quantized=True
    )
    assert btc_budget in (10000, 16000)

def test_providers_set_thinking_budget_quantization():
    anthropic_p = AnthropicProvider(model="claude-sonnet-4-6", settings={})
    anthropic_p.set_thinking_budget(3248)
    assert anthropic_p.thinking_budget == 4096
    assert anthropic_p.thinking_level == "medium"

    anthropic_p.set_thinking_budget(8500)
    assert anthropic_p.thinking_budget == 10000
    assert anthropic_p.thinking_level == "high"

    anthropic_p.set_thinking_budget(0)
    assert anthropic_p.thinking_budget == 0
    assert anthropic_p.thinking_level == "none"

    gemini_p = GeminiProvider(model="gemini-3.5-flash", settings={})
    gemini_p.set_thinking_budget(5120)
    assert gemini_p.thinking_budget == 4096
    assert gemini_p.resolved_thinking_level == "MEDIUM"

    openai_p = OpenAIProvider(model="gpt-4o", settings={})
    openai_p.set_thinking_budget(2100)
    assert openai_p.thinking_budget == 1024
    assert openai_p.thinking_level == "low"
