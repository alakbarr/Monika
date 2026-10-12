import pytest
import time
from unittest.mock import MagicMock
from analysis.providers.llm_factory import LLMFactory, FallbackClientWrapper


@pytest.fixture
def mock_factory_and_wrapper():
    settings = {
        "llm": {
            "providers": {"anthropic": {"enabled": True}, "gemini": {"enabled": True}},
            "model_catalog": {
                "claude-sonnet-5": {"provider": "anthropic"},
                "gemini-2.5-flash": {"provider": "gemini"},
            },
            "task_roles": {
                "test_role": {
                    "primary": "claude-sonnet-5",
                    "fallback_1": "gemini-2.5-flash",
                }
            },
        }
    }
    factory = LLMFactory(settings)
    wrapper = FallbackClientWrapper(
        factory=factory,
        primary="claude-sonnet-5",
        fallbacks=["gemini-2.5-flash"],
        role_config={"max_tokens": 100, "max_tool_turns": 2},
        task_role="test_role",
    )
    return factory, wrapper


def test_maybe_restore_primary_no_cooldown(mock_factory_and_wrapper):
    _, wrapper = mock_factory_and_wrapper
    assert wrapper._primary_cooldown_until is None
    assert wrapper._maybe_restore_primary() is False


def test_maybe_restore_primary_cooling_down(mock_factory_and_wrapper):
    _, wrapper = mock_factory_and_wrapper
    wrapper._primary_cooldown_until = time.time() + 100.0  # Future
    assert wrapper._maybe_restore_primary() is False
    assert wrapper._primary_cooldown_until is not None


def test_maybe_restore_primary_expired(mock_factory_and_wrapper):
    _, wrapper = mock_factory_and_wrapper
    wrapper._primary_cooldown_until = time.time() - 1.0  # Past
    assert wrapper._maybe_restore_primary() is True
    assert wrapper._primary_cooldown_until is None
