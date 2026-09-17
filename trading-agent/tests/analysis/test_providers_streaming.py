# ==============================================================================
# File: tests/analysis/test_providers_streaming.py
# ==============================================================================

"""Integration unit tests for provider streaming implementations."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from types import SimpleNamespace

from analysis.providers.gemini_provider import GeminiProvider
from analysis.providers.anthropic_provider import AnthropicProvider
from analysis.providers.openai_provider import OpenAIProvider
from analysis.providers.llm_factory import LLMFactory
from utils.api.streaming import StreamTimeoutError, StreamConfig, StreamResult


SAMPLE_SETTINGS = {
    "llm": {
        "providers": {
            "gemini": {
                "enabled": True,
                "streaming": {
                    "enabled": True,
                    "idle_timeout_seconds": 45,
                    "first_chunk_timeout_seconds": 90,
                    "safety_timeout_seconds": 600,
                },
                "timeout_seconds": 120,
            },
            "anthropic": {
                "enabled": True,
                "streaming": {
                    "enabled": True,
                    "idle_timeout_seconds": 30,
                    "first_chunk_timeout_seconds": 60,
                    "safety_timeout_seconds": 600,
                },
                "timeout_seconds": 120,
            },
            "openai": {
                "enabled": True,
                "streaming": {
                    "enabled": True,
                    "idle_timeout_seconds": 45,
                    "first_chunk_timeout_seconds": 90,
                    "safety_timeout_seconds": 600,
                },
                "timeout_seconds": 120,
            },
            "openrouter": {
                "enabled": True,
                "streaming": {
                    "enabled": True,
                    "idle_timeout_seconds": 45,
                    "first_chunk_timeout_seconds": 120,
                    "safety_timeout_seconds": 600,
                },
                "timeout_seconds": 120,
            },
            "groq": {
                "enabled": True,
                "streaming": {
                    "enabled": True,
                    "idle_timeout_seconds": 15,
                    "first_chunk_timeout_seconds": 30,
                    "safety_timeout_seconds": 300,
                },
                "timeout_seconds": 120,
            },
        },
        "model_catalog": {
            "gemini-3.7-flash": {"provider": "gemini"},
            "gemini-3.5-flash": {"provider": "gemini"},
            "gpt-4o": {"provider": "openai"},
            "claude-sonnet-4-6": {"provider": "anthropic"},
        },
        "task_roles": {
            "debate_judge": {
                "primary": "gemini-3.7-flash",
                "fallback_1": "gemini-3.5-flash",
                "max_tokens": 4096,
            }
        }
    }
}


def test_gemini_build_stream_config():
    """Verify GeminiProvider builds StreamConfig from settings."""
    provider = GeminiProvider("gemini-3.7-flash", settings=SAMPLE_SETTINGS)
    cfg = provider._build_stream_config()
    assert cfg.idle_timeout == 45.0
    assert cfg.first_chunk_timeout == 90.0
    assert cfg.safety_timeout == 600.0


def test_anthropic_build_stream_config():
    """Verify AnthropicProvider builds StreamConfig from settings."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        provider = AnthropicProvider("claude-sonnet-4-6", settings=SAMPLE_SETTINGS)
        cfg = provider._build_stream_config()
        assert cfg.idle_timeout == 30.0
        assert cfg.first_chunk_timeout == 60.0


def test_openai_build_stream_config():
    """Verify OpenAIProvider builds StreamConfig from settings."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider("gpt-4o", settings=SAMPLE_SETTINGS)
        cfg = provider._build_stream_config()
        assert cfg.idle_timeout == 45.0
        assert cfg.first_chunk_timeout == 90.0


@pytest.mark.asyncio
async def test_gemini_generate_calls_streaming_request():
    """Verify GeminiProvider.generate calls streaming_request with streamGenerateContent?alt=sse."""
    provider = GeminiProvider("gemini-3.7-flash", settings=SAMPLE_SETTINGS)
    provider.free_api_keys = ["mock-key-1"]

    mock_result = StreamResult(
        text='{"verdict": "BULLISH"}',
        finish_reason="STOP",
        usage={"promptTokenCount": 50, "candidatesTokenCount": 20}
    )

    with patch("analysis.providers.gemini_provider.streaming_request", new_callable=AsyncMock) as mock_stream_req:
        mock_stream_req.return_value = mock_result
        with patch.object(provider, "_save_token_usage", new_callable=AsyncMock):
            with patch("analysis.providers.gemini_provider.get_session"):
                with patch("analysis.providers.gemini_provider.GeminiRateLimiter.try_acquire", return_value=True):
                    res = await provider.generate("Evaluate macro conditions")

                    assert res == '{"verdict": "BULLISH"}'
                    assert mock_stream_req.called
                    call_url = mock_stream_req.call_args[0][0]
                    assert "streamGenerateContent?alt=sse" in call_url


@pytest.mark.asyncio
async def test_fallback_on_stream_timeout():
    """Verify that StreamTimeoutError triggers the next fallback model in LLMFactory."""
    factory = LLMFactory(SAMPLE_SETTINGS)
    wrapper = factory.get_client_for_task("debate_judge")

    primary_client = MagicMock()
    primary_client.classify_json = AsyncMock(
        side_effect=StreamTimeoutError("Streaming idle timeout (45s)", idle_seconds=45.0, chunks_received=3)
    )

    fallback_client = MagicMock()
    fallback_client.classify_json = AsyncMock(
        return_value={"winner": "BULL", "confidence": 0.85}
    )

    def mock_create_instance(model_name, role_config, slot_name=None, task_role=None):
        if slot_name == "primary":
            return primary_client
        return fallback_client

    with patch.object(factory, "_create_client_instance", side_effect=mock_create_instance):
        result = await wrapper.classify_json("Judge the debate arguments")

        assert result == {"winner": "BULL", "confidence": 0.85}
        assert primary_client.classify_json.called
        assert fallback_client.classify_json.called
