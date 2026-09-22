"""
Unit tests for Monika v2 Per-Role Fallback Chain & Cost-Aware Routing (PR-03).
Tests list-based fallback configuration, deduplication, and max_cost_per_call guidance.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from analysis.providers.llm_factory import LLMFactory, FallbackClientWrapper
from config.schemas import TaskRoleConfig


def test_task_role_config_schema_validation():
    # Test list format fallback
    cfg = TaskRoleConfig(
        primary="gemini-3.5-flash-lite",
        fallback=["gemini-3.1-flash-lite", "openrouter/free"],
        max_cost_per_call=0.05,
    )
    assert cfg.primary == "gemini-3.5-flash-lite"
    assert cfg.fallback == ["gemini-3.1-flash-lite", "openrouter/free"]
    assert cfg.max_cost_per_call == 0.05

    # Test backward-compatible numbered fallback slots
    cfg_legacy = TaskRoleConfig(
        primary="gemini-3.5-flash-lite",
        fallback_1="gemini-3.1-flash-lite",
        fallback_2="openrouter/free",
    )
    assert cfg_legacy.fallback_1 == "gemini-3.1-flash-lite"
    assert cfg_legacy.fallback_2 == "openrouter/free"


def test_llm_factory_parses_list_fallback_chain():
    settings = {
        "llm": {
            "task_roles": {
                "custom_role": {
                    "primary": "gemini-3.5-flash-lite",
                    "fallback": ["gemini-3.1-flash-lite", "groq-compound"],
                    "max_cost_per_call": 0.05,
                }
            },
            "model_catalog": {
                "gemini-3.5-flash-lite": {"provider": "gemini"},
                "gemini-3.1-flash-lite": {"provider": "gemini"},
                "groq-compound": {"provider": "groq"},
            }
        }
    }
    factory = LLMFactory(settings)
    client = factory.get_client_for_task("custom_role")

    assert isinstance(client, FallbackClientWrapper)
    assert client.primary == "gemini-3.5-flash-lite"
    assert client.fallbacks == ["gemini-3.1-flash-lite", "groq-compound"]
    assert client.max_cost_per_call == 0.05


def test_llm_factory_combines_list_and_numbered_fallbacks():
    settings = {
        "llm": {
            "task_roles": {
                "mixed_role": {
                    "primary": "gemini-3.5-flash-lite",
                    "fallback": ["gemini-3.1-flash-lite"],
                    "fallback_1": "gemini-3.1-flash-lite",  # duplicate, should be deduped
                    "fallback_2": "groq-compound",
                }
            },
            "model_catalog": {
                "gemini-3.5-flash-lite": {"provider": "gemini"},
                "gemini-3.1-flash-lite": {"provider": "gemini"},
                "groq-compound": {"provider": "groq"},
            }
        }
    }
    factory = LLMFactory(settings)
    client = factory.get_client_for_task("mixed_role")

    assert client.fallbacks == ["gemini-3.1-flash-lite", "groq-compound"]


@pytest.mark.asyncio
async def test_fallback_client_wrapper_cost_warning(caplog):
    settings = {
        "llm": {
            "model_catalog": {
                "gemini-3.5-flash-lite": {"provider": "gemini"},
                "claude-opus-5": {"provider": "anthropic"},
            }
        }
    }
    factory = LLMFactory(settings)
    role_config = {
        "primary": "gemini-3.5-flash-lite",
        "fallback_1": "claude-opus-5",
        "max_cost_per_call": 0.001,  # very low ceiling ($0.001)
        "max_tokens": 16384,
    }

    wrapper = FallbackClientWrapper(
        factory=factory,
        primary="gemini-3.5-flash-lite",
        fallbacks=["claude-opus-5"],
        role_config=role_config,
        task_role="test_budget_role",
    )

    mock_cheap = MagicMock()
    # Non-retryable error to fail over immediately without backoff delay
    mock_cheap.generate = AsyncMock(side_effect=RuntimeError("Model service unavailable 503"))

    mock_exp = MagicMock()
    mock_exp.generate = AsyncMock(return_value="Success from expensive model")

    def mock_create_instance(model, cfg, slot_name=None):
        if model == "gemini-3.5-flash-lite":
            return mock_cheap
        return mock_exp

    factory._create_client_instance = mock_create_instance

    with caplog.at_level("WARNING"):
        res = await wrapper.generate("test prompt")
        assert res == "Success from expensive model"

    assert any("exceeds max_cost_per_call" in record.message for record in caplog.records)
