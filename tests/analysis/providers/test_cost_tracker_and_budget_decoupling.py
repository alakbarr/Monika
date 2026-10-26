import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from monika.core.analytics.pricing import (
    cost_usd,
    cost_usd_decimal,
    is_paid_model,
    is_free_tier,
)
from monika.infrastructure.providers.llm_factory import LLMFactory
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.database.models import TokenUsageLog


class TestCostTrackingAndBudgetDecoupling:
    def test_is_paid_model_and_free_tier_rules(self):
        """Test accurate classification of paid vs free models across all providers."""
        # 1. OpenRouter free endpoints
        assert is_paid_model("openrouter/free") is False
        assert is_free_tier("openrouter/free") is True
        assert is_paid_model("meta-llama/llama-3.3-70b-instruct:free") is False

        # 2. OpenRouter paid models
        assert is_paid_model("deepseek-v4.1-flash-1017", provider="openrouter") is True
        assert is_paid_model("minimax-m3.1-flash", provider="openrouter") is True
        assert is_paid_model("gemini-4-argon", provider="openrouter") is True

        # 3. Gemini key tiers
        # Direct Gemini AI Studio defaults to free pool
        assert is_paid_model("gemini-2.5-flash", provider="gemini") is False
        assert is_paid_model("gemini-2.5-flash-lite", provider="gemini") is False
        # When slot specifies paid tier (GEMINI_PAID_API_KEY)
        assert is_paid_model("gemini-2.5-flash", provider="gemini", is_direct_free_tier=False) is True
        assert is_paid_model("gemini-2.5-flash-lite", provider="gemini", is_direct_free_tier=False) is True
        # Explicit free pool
        assert is_paid_model("gemini-2.5-flash", provider="gemini", is_direct_free_tier=True) is False

        # 4. Anthropic & OpenAI paid
        assert is_paid_model("claude-opus-5.5", provider="anthropic") is True
        assert is_paid_model("gpt-6.1-sol", provider="openai") is True

    def test_factory_is_model_paid_with_slot_tier_override(self):
        """Test LLMFactory.is_model_paid honors slot-level tier overrides."""
        factory = LLMFactory(settings={})

        role_cfg_default = {"provider": "gemini"}
        assert factory.is_model_paid("gemini-2.5-flash", role_config=role_cfg_default, slot_name="primary") is False

        # Slot explicitly configured with paid tier
        role_cfg_paid = {"provider": "gemini", "primary_gemini_tier": "paid"}
        assert factory.is_model_paid("gemini-2.5-flash", role_config=role_cfg_paid, slot_name="primary") is True

        # Fallback slot configured with free tier
        role_cfg_mixed = {"provider": "gemini", "primary_tier": "paid", "fallback_1_tier": "free"}
        assert factory.is_model_paid("gemini-2.5-flash", role_config=role_cfg_mixed, slot_name="primary") is True
        assert factory.is_model_paid("gemini-2.5-flash", role_config=role_cfg_mixed, slot_name="fallback_1") is False

    @pytest.mark.asyncio
    async def test_fallback_wrapper_bypasses_paid_slots_when_budget_paused(self):
        """
        Critical verification: When CostTracker.is_budget_paused_cached() is True,
        FallbackClientWrapper skips paid primary/fallbacks and executes the first free candidate.
        """
        factory = LLMFactory(settings={})

        primary_paid = "deepseek-v4.1-flash-1017"
        fallback_free = "gemini-2.5-flash"

        role_config = {
            "primary": primary_paid,
            "fallback_1": fallback_free,
            "provider": {"primary": "openrouter", "fallback_1": "gemini"},
        }

        wrapper = factory._create_client_with_fallback(
            primary=primary_paid,
            fallbacks=[fallback_free],
            role_config=role_config,
            task_role="stage2_per_asset_primary",
        )

        mock_paid_client = MagicMock()
        mock_paid_client.generate = AsyncMock(return_value="paid_output")

        mock_free_client = MagicMock()
        mock_free_client.generate = AsyncMock(return_value='{"decision": "BUY", "confidence": 0.8}')

        def mock_create_client(model, r_cfg, slot_name=None, task_role=None):
            if model == primary_paid:
                return mock_paid_client
            return mock_free_client

        with patch.object(factory, "_create_client_instance", side_effect=mock_create_client):
            # 1. When budget is healthy (paused=False) -> Primary paid model is called
            with patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused_cached", return_value=False):
                res = await wrapper.generate("test prompt")
                assert res == "paid_output"
                mock_paid_client.generate.assert_called_once()
                mock_free_client.generate.assert_not_called()

            mock_paid_client.generate.reset_mock()
            mock_free_client.generate.reset_mock()

            # 2. When budget IS PAUSED (paused=True) -> Paid model is bypassed; free candidate executes!
            with patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused_cached", return_value=True):
                res = await wrapper.generate("test prompt")
                assert res == '{"decision": "BUY", "confidence": 0.8}'
                mock_paid_client.generate.assert_not_called()
                mock_free_client.generate.assert_called_once()

    def test_openrouter_extract_usage_cost_ingestion(self):
        """Test extraction of OpenRouter usage.cost from standard and model_extra fields."""

        # 1. Direct usage.cost attribute
        class MockUsage1:
            prompt_tokens = 1200
            completion_tokens = 300
            cost = 0.00045

        inp, outp, cached, thinking, exact_cost, creation = OpenAIProvider._extract_usage(MockUsage1())
        assert inp == 1200
        assert outp == 300
        assert exact_cost == 0.00045

        # 2. Pydantic model_extra['cost'] attribute
        class MockUsage2:
            prompt_tokens = 800
            completion_tokens = 200
            model_extra = {"cost": 0.00028}

        inp, outp, cached, thinking, exact_cost, creation = OpenAIProvider._extract_usage(MockUsage2())
        assert inp == 800
        assert outp == 200
        assert exact_cost == 0.00028

        # 3. Dict usage with cost
        usage_dict = {"prompt_tokens": 500, "completion_tokens": 100, "cost": 0.00015}
        inp, outp, cached, thinking, exact_cost, creation = OpenAIProvider._extract_usage(usage_dict)
        assert exact_cost == 0.00015

    def test_token_usage_log_schema_attributes(self):
        """Verify is_paid and cost_source exist on TokenUsageLog domain model."""
        log = TokenUsageLog(
            provider="gemini",
            model_name="gemini-2.5-flash",
            task_name="generate",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            is_paid=False,
            cost_source="gemini_free_tier",
            cost_estimate=0.0,
        )
        assert log.is_paid is False
        assert log.cost_source == "gemini_free_tier"
        assert log.cost_estimate == 0.0
