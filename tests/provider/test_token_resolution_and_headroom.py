import yaml

"""
Unit tests for Multi-Tier Dynamic Token Resolution and Headroom Allocation.
Verifies that max_tokens is maximized according to model/provider hardware and API ceilings,
thinking_budget is preserved without starving answer headroom, and strict ceiling models
(such as Groq and DeepSeek direct) never exceed their allowed limits.
"""

import pytest
from monika.infrastructure.providers.capabilities import (
    get_model_capabilities,
    resolve_effective_max_tokens,
)
from monika.infrastructure.llm.adaptive_thinking import (
    clamp_thinking_budget_to_answer_room,
)
from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider
from monika.infrastructure.providers.openai_provider import OpenAIProvider


class TestTokenResolutionCeilings:
    """Tests for resolve_effective_max_tokens across model families and providers."""

    def test_openrouter_deepseek_paid_thinking_expansion(self):
        """Paid DeepSeek model on OpenRouter with high/max thinking must expand beyond 8192."""
        eff = resolve_effective_max_tokens(
            model_name="deepseek-v4.1-flash-1017",
            provider_name="openrouter",
            requested_max_tokens=8192,
            thinking_level="high",
            thinking_budget=8192,
        )
        # 8192 thinking + 4096 headroom = 12288, or requested 8192 + 8192 = 16384
        assert eff >= 16384, f"Expected effective max_tokens >= 16384, got {eff}"
        assert eff <= 32768

    def test_openrouter_deepseek_max_thinking_level(self):
        """Level 'max' (budget 16000) on DeepSeek OpenRouter must allocate enough headroom."""
        eff = resolve_effective_max_tokens(
            model_name="deepseek-v4.1-flash",
            provider_name="openrouter",
            requested_max_tokens=8192,
            thinking_level="max",
            thinking_budget=16000,
        )
        assert eff >= 20096, f"Expected effective max_tokens >= 20096, got {eff}"
        assert eff <= 32768

    def test_claude_3_7_sonnet_thinking_ceiling(self):
        """Claude 3.7 Sonnet must support up to 64,000 output tokens with thinking."""
        eff = resolve_effective_max_tokens(
            model_name="claude-3-7-sonnet",
            provider_name="anthropic",
            requested_max_tokens=8192,
            thinking_level="max",
            thinking_budget=20000,
        )
        assert eff >= 24096
        assert eff <= 64000

    def test_gemini_2_5_flash_thinking_ceiling(self):
        """Gemini 2.5 Flash must support up to 65,536 output tokens with thinking."""
        eff = resolve_effective_max_tokens(
            model_name="gemini-2.5-flash",
            provider_name="gemini",
            requested_max_tokens=8192,
            thinking_level="max",
            thinking_budget=24000,
        )
        assert eff >= 28096
        assert eff <= 65536

    def test_openai_o3_mini_completion_tokens(self):
        """OpenAI o3-mini must support large completion token ceilings."""
        eff = resolve_effective_max_tokens(
            model_name="o3-mini",
            provider_name="openai",
            requested_max_tokens=8192,
            thinking_level="high",
            thinking_budget=16000,
        )
        assert eff >= 20096
        assert eff <= 65536

    def test_groq_strict_ceiling_protection(self):
        """Groq models must strictly never exceed hardware/API limits to avoid HTTP 400."""
        # 8B / Compound hard limit is 8,192
        eff_compound = resolve_effective_max_tokens(
            model_name="groq-compound",
            provider_name="groq",
            requested_max_tokens=16384,
            thinking_level="high",
            thinking_budget=8192,
        )
        assert eff_compound == 8192, f"Groq compound must be strictly capped at 8192, got {eff_compound}"

        # 70B hard limit is 32,768
        eff_70b = resolve_effective_max_tokens(
            model_name="llama-3.3-70b",
            provider_name="groq",
            requested_max_tokens=65536,
            thinking_level="max",
            thinking_budget=16000,
        )
        assert eff_70b <= 32768, f"Groq 70B must be capped at 32768, got {eff_70b}"

    def test_deepseek_direct_api_strict_ceiling(self):
        """DeepSeek direct API enforces 8,192 hard completion limit."""
        eff = resolve_effective_max_tokens(
            model_name="deepseek-reasoner",
            provider_name="deepseek",
            requested_max_tokens=16384,
            thinking_level="high",
            thinking_budget=8192,
        )
        assert eff == 8192, f"DeepSeek direct API must be strictly capped at 8192, got {eff}"

    def test_non_thinking_mode_respects_request_and_ceiling(self):
        """When thinking is none, max_tokens respects requested tokens up to model ceiling."""
        eff = resolve_effective_max_tokens(
            model_name="gpt-4o",
            provider_name="openai",
            requested_max_tokens=4096,
            thinking_level="none",
        )
        assert eff == 4096

        eff_default = resolve_effective_max_tokens(
            model_name="gpt-4o",
            provider_name="openai",
            requested_max_tokens=None,
            thinking_level="none",
        )
        assert eff_default == 8192


class TestThinkingBudgetHeadroomClamping:
    """Tests for clamp_thinking_budget_to_answer_room and answer preservation."""

    def test_backward_compatibility(self):
        """Existing test contract: budget=10000, max_tokens=8192, min_answer_tokens=1024 -> 7168."""
        clamped = clamp_thinking_budget_to_answer_room(budget=10000, max_tokens=8192, min_answer_tokens=1024)
        assert clamped == 7168

    def test_expanded_max_tokens_prevents_starvation(self):
        """With expanded max_tokens (e.g. 24192), a 16000 budget is fully preserved."""
        clamped = clamp_thinking_budget_to_answer_room(budget=16000, max_tokens=24192, min_answer_tokens=4096)
        assert clamped == 16000
        # Answer headroom is 24192 - 16000 = 8192 tokens!
        assert (24192 - clamped) >= 4096

    def test_ratio_clamping(self):
        """Optional max_thinking_ratio caps thinking at given percentage of max_tokens."""
        clamped = clamp_thinking_budget_to_answer_room(
            budget=10000, max_tokens=8192, min_answer_tokens=1024, max_thinking_ratio=0.6
        )
        # 60% of 8192 is 4915
        assert clamped == 4915
        assert (8192 - clamped) >= 3277


class TestOpenRouterProviderReasoningParams:
    """Tests for OpenRouterProvider reasoning parameter handling."""

    def test_paid_model_receives_expanded_max_tokens(self):
        """Paid models (is_free=False) must not be stuck at 8192 when thinking is active."""
        provider = OpenRouterProvider(
            model="deepseek-v4.1-flash-1017",
            max_tokens=8192,
            thinking_level="high",
            api_key="sk-or-dummy-key",
        )
        kwargs = {"model": provider.model, "messages": [], "max_tokens": 8192}
        provider._apply_reasoning_params(kwargs)

        assert kwargs.get("max_tokens") >= 16384, (
            f"Expected max_tokens >= 16384 for paid thinking model, got {kwargs.get('max_tokens')}"
        )
        assert "extra_body" in kwargs
        assert kwargs["extra_body"].get("reasoning") == {"effort": "high"}

    def test_non_thinking_cleans_reasoning_body(self):
        """When thinking_level is none, reasoning extra_body is removed."""
        provider = OpenRouterProvider(
            model="deepseek-v4.1-flash-1017",
            max_tokens=8192,
            thinking_level="none",
            api_key="sk-or-dummy-key",
        )
        kwargs = {
            "model": provider.model,
            "messages": [],
            "max_tokens": 8192,
            "extra_body": {"reasoning": {"effort": "high"}},
        }
        provider._apply_reasoning_params(kwargs)

        assert "reasoning" not in kwargs.get("extra_body", {})
        assert kwargs.get("max_tokens") <= 32768


class TestOpenAIProviderReasoningParams:
    """Tests for OpenAIProvider reasoning parameter handling."""

    def test_reasoning_model_uses_max_completion_tokens(self):
        """OpenAI reasoning models (o3-mini, o1) must use max_completion_tokens and pop max_tokens."""
        provider = OpenAIProvider(
            model="o3-mini",
            max_tokens=8192,
            thinking_level="high",
            api_key="sk-dummy-key",
        )
        kwargs = {"model": provider.model, "messages": [], "max_tokens": 8192}
        provider._apply_reasoning_params(kwargs)

        assert "max_tokens" not in kwargs
        assert "max_completion_tokens" in kwargs
        assert kwargs["max_completion_tokens"] >= 16384


class TestFullCatalogNormalizationAndResolution:
    """Tests covering full catalog prefix stripping, vendor canonicalization, and headroom resolution."""

    def test_routed_models_do_not_clamp_to_8192(self):
        """Routed 9router/aggregator prefixes must not be artificially clamped to 8192."""
        test_cases = [
            ("kr/claude-sonnet-4.5-thinking", 64000),
            ("ocz/deepseek-v4-flash-free", 32768),
            ("af/gpt-oss-120b", 65536),
            ("nvidia/nemotron-3-ultra-550b-a55b:free", 32768),
            ("cx/gpt-5.6-sol", 65536),
            ("if/deepseek-r1", 65536),
            ("ag/gemini-3.8-flash-high", 65536),
            ("kr/qwen3-coder-next", 32768),
        ]
        for model_name, min_expected_cap in test_cases:
            caps = get_model_capabilities(model_name)
            assert caps.max_output_tokens >= min_expected_cap, (
                f"Model {model_name} capped at {caps.max_output_tokens}, expected >= {min_expected_cap}"
            )

    def test_all_catalog_models_resolve_safely(self):
        """Every model in model_catalog must successfully resolve capabilities without error."""
        with open("config/settings.example.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        catalog = cfg.get("llm", {}).get("model_catalog", {})
        assert len(catalog) >= 190, f"Expected at least 190 models in catalog, found {len(catalog)}"

        for model_name, meta in catalog.items():
            caps = get_model_capabilities(model_name)
            assert caps is not None
            assert caps.max_output_tokens >= 448  # Lowest is whisper 448
            assert caps.context_window >= 16000

            eff = resolve_effective_max_tokens(
                model_name=model_name,
                provider_name=meta.get("provider", "openrouter"),
                requested_max_tokens=8192,
                thinking_level="high",
                thinking_budget=8192,
            )
            assert eff >= 448

    def test_thinking_headroom_across_frontier_families(self):
        """Frontier models must expand to accommodate both thinking budget and visible answer headroom."""
        frontier_models = [
            ("claude-sonnet-4.5", "anthropic", 64000),
            ("deepseek-v4.1-flash-1017", "openrouter", 32768),
            ("gemini-3.5-flash", "gemini", 65536),
            ("gpt-5.6-luna", "openai", 65536),
            ("qwen3.8-27b", "openrouter", 32768),
        ]
        for model_name, prov, ceiling in frontier_models:
            eff = resolve_effective_max_tokens(
                model_name=model_name,
                provider_name=prov,
                requested_max_tokens=8192,
                thinking_level="high",
                thinking_budget=8192,
            )
            assert eff >= 16384, f"{model_name} on {prov} failed to expand: eff={eff}"
            assert eff <= ceiling
