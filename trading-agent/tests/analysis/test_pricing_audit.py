"""
Unit test untuk pricing and prompt caching discount calculation,
serta audit kelengkapan 100% model di settings.yaml.
"""
import os
import yaml
from pathlib import Path
from utils.analytics.pricing import cost_usd, get_price, PRICING, OPENROUTER_PRICING_MAP, FREE_TIER_MODELS
import benchmark.pricing as benchmark_pricing


def test_pricing_without_cache():
    # claude-sonnet-5: in=2.00/1M, out=10.00/1M
    cost = cost_usd("claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000, cached_tokens=0)
    assert cost == 12.0


def test_pricing_with_cache():
    # claude-sonnet-5: in=2.00/1M, cached_in=0.20/1M, out=10.00/1M
    # 500k normal input ($1.00) + 500k cached input ($0.10) + 1M output ($10.00) = $11.10
    cost = cost_usd("claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000, cached_tokens=500_000)
    assert cost == 11.10


def test_pricing_free_tier():
    assert cost_usd("z-ai/glm-5.2:free", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0
    assert cost_usd("groq-compound", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0
    assert cost_usd("llama3.2", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0
    assert cost_usd("ox-alpha", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0
    assert cost_usd("gemini-3.5-flash-lite", 1_000_000, 1_000_000, provider="gemini") == 0.0
    assert cost_usd("gemini-3.5-flash", 1_000_000, 1_000_000, provider="gemini") == 0.0
    assert cost_usd("groq-compound", 1_000_000, 1_000_000, provider="groq") == 0.0
    assert cost_usd("llama3.2", 1_000_000, 1_000_000, provider="ollama") == 0.0
    assert cost_usd("claude-sonnet-5", 1_000_000, 1_000_000, is_direct_free_tier=True) == 0.0


def test_specific_model_pricing_accuracy():
    """Menguji akurasi harga model-model kunci dari berbagai provider."""
    # Kimi K3: in=3.00, out=15.00
    assert cost_usd("kimi-k3", 1_000_000, 1_000_000) == 18.0
    assert cost_usd("moonshotai/kimi-k3", 1_000_000, 1_000_000) == 18.0

    # Qwen 3.8 Max: in=1.60, out=6.40
    assert cost_usd("qwen3.8-max", 1_000_000, 1_000_000) == 8.0

    # Grok 4.5: in=3.00, out=15.00
    assert cost_usd("grok-4.5", 1_000_000, 1_000_000) == 18.0

    # MiMo v2.5 Pro: in=0.50, out=2.00
    assert cost_usd("mimo-v2.5-pro", 1_000_000, 1_000_000) == 2.50

    # DeepSeek V4 Pro: in=0.66, out=1.98
    assert cost_usd("deepseek-v4-pro", 1_000_000, 1_000_000) == 2.64

    # Gemini 3.5 Flash Lite: in=0.30, out=2.50 (Paid Tier rate)
    assert cost_usd("gemini-3.5-flash-lite", 1_000_000, 1_000_000, is_direct_free_tier=False) == 2.80


def test_all_settings_yaml_models_covered():
    """Memverifikasi bahwa 100% model di settings.yaml:model_catalog memiliki harga valid."""
    settings_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(settings_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    catalog = cfg.get("llm", {}).get("model_catalog", {})
    assert len(catalog) > 0, "model_catalog di settings.yaml tidak boleh kosong"

    for model_name in catalog.keys():
        price = get_price(model_name)
        assert price is not None, f"Model {model_name} tidak menghasilkan objek Price"
        assert price.input >= 0.0, f"Model {model_name} input price negatif"
        assert price.output >= 0.0, f"Model {model_name} output price negatif"
        cost = cost_usd(model_name, 1000, 1000)
        assert cost >= 0.0, f"Model {model_name} cost_usd negatif"


def test_benchmark_pricing_backward_compatibility():
    """Memverifikasi bahwa benchmark.pricing mengekspor semua fungsi dari utils.analytics.pricing."""
    assert benchmark_pricing.cost_usd("claude-sonnet-5", 1000, 1000) == cost_usd("claude-sonnet-5", 1000, 1000)
    assert benchmark_pricing.get_price("kimi-k3") == get_price("kimi-k3")
    assert "claude-opus-5" in benchmark_pricing.PRICING
