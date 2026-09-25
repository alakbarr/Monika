"""
Unit tests for NineRouterProvider (9Router / NymRouter integration).
Tests initialization, model normalization, free tier recognition,
capabilities, dynamic discovery, and factory integration.
"""

import pytest
import unittest.mock as mock
from analysis.providers.nine_router_provider import (
    NineRouterProvider,
    normalize_9router_model_name,
    FREE_TIER_MODELS_9ROUTER,
)
from analysis.providers.provider_registry import ProviderRegistry
from analysis.providers.llm_factory import LLMFactory
from analysis.providers.capabilities import get_model_capabilities, resolve_effective_context_window
from utils.analytics.pricing import is_free_tier, infer_provider_from_model


@pytest.fixture
def mock_settings():
    return {
        "llm": {
            "providers": {
                "ninerouter": {
                    "enabled": True,
                    "base_url": "http://localhost:20128/v1",
                    "timeout_seconds": 60.0,
                    "max_retries": 2,
                }
            },
            "model_catalog": {
                "kr/claude-sonnet-4.5": {
                    "provider": "9router",
                    "context_window": 200000,
                    "supports_tool_calling": True,
                    "cost_tier": "free",
                }
            },
            "task_roles": {}
        }
    }


def test_nine_router_initialization_defaults(mock_settings, monkeypatch):
    monkeypatch.delenv("NINEROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NINEROUTER_KEY", raising=False)
    monkeypatch.delenv("NINEROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("NINEROUTER_URL", raising=False)
    provider = NineRouterProvider(
        model="kr/claude-sonnet-4.5",
        settings=mock_settings
    )
    assert provider.provider_name == "9router"
    assert provider.model == "kr/claude-sonnet-4.5"
    assert provider.base_url == "http://localhost:20128/v1"
    assert provider.api_key == "sk-9router-local"
    assert provider.is_free is True


def test_nine_router_initialization_custom_url(mock_settings):
    provider = NineRouterProvider(
        model="if/kimi-k2",
        base_url="http://192.168.1.100:20128/v1",
        api_key="custom-test-key",
        settings=mock_settings
    )
    assert provider.base_url == "http://192.168.1.100:20128/v1"
    assert provider.api_key == "custom-test-key"
    assert provider.model == "if/kimi-k2"
    assert provider.is_free is True


def test_nine_router_model_normalization():
    assert normalize_9router_model_name("9r/kr/claude-sonnet-4.5") == "kr/claude-sonnet-4.5"
    assert normalize_9router_model_name("9router/if/kimi-k2") == "if/kimi-k2"
    assert normalize_9router_model_name("oc/union-alpha") == "oc/union-alpha"
    assert normalize_9router_model_name("combo/free-fallback") == "combo/free-fallback"
    assert normalize_9router_model_name("9r/combo/smart-code") == "combo/smart-code"


def test_nine_router_free_tier_recognition(mock_settings):
    provider = NineRouterProvider(model="kr/claude-sonnet-4.5", settings=mock_settings)

    # Model gratis Kiro, OpenCode, iFlow, MiMo
    assert provider.is_model_free("kr/claude-sonnet-4.5") is True
    assert provider.is_model_free("kr/claude-opus-5") is True
    assert provider.is_model_free("oc/union-alpha") is True
    assert provider.is_model_free("if/kimi-k2") is True
    assert provider.is_model_free("mmf/mimo-auto") is True
    assert provider.is_model_free("combo/free-fallback") is True
    assert provider.is_model_free("custom-model:free") is True

    # Model berbayar upstream
    assert provider.is_model_free("ag/gemini-3.8-flash-high") is False
    assert provider.is_model_free("cx/gpt-5.6-sol") is False


def test_pricing_module_integration():
    # Provider inference
    assert infer_provider_from_model("kr/claude-sonnet-4.5") == "9router"
    assert infer_provider_from_model("if/kimi-k2") == "9router"
    assert infer_provider_from_model("oc/union-alpha") == "9router"
    assert infer_provider_from_model("9r/custom-model") == "9router"
    assert infer_provider_from_model("9router/custom-model") == "9router"

    # Free tier verification
    assert is_free_tier("kr/claude-sonnet-4.5") is True
    assert is_free_tier("if/kimi-k2") is True
    assert is_free_tier("oc/union-alpha") is True
    assert is_free_tier("9r/kr/claude-sonnet-4.5") is True
    assert is_free_tier("ag/gemini-3.8-flash-high") is False


def test_capabilities_and_context_window():
    caps = get_model_capabilities("kr/claude-sonnet-4.5")
    assert caps.supports_structured_output is True
    assert caps.context_window == 200000

    caps_if = get_model_capabilities("if/kimi-k2")
    assert caps_if.supports_structured_output is True
    assert caps_if.context_window == 128000

    # Prefix stripping capability
    caps_9r = get_model_capabilities("9r/kr/claude-sonnet-4.5")
    assert caps_9r.context_window == 200000

    # Effective context window resolution
    ctx = resolve_effective_context_window("kr/claude-sonnet-4.5", "9router")
    assert ctx == 200000


def test_llm_factory_and_registry_resolution(mock_settings):
    factory = LLMFactory(mock_settings)

    # Resolution via prefix
    assert factory._resolve_provider("kr/claude-sonnet-4.5") == "9router"
    assert factory._resolve_provider("if/kimi-k2") == "9router"
    assert factory._resolve_provider("oc/union-alpha") == "9router"
    assert factory._resolve_provider("ocz/deepseek-v4-flash-free") == "9router"
    assert factory._resolve_provider("mmf/mimo-auto") == "9router"
    assert factory._resolve_provider("gc/gemini-2.5-flash") == "9router"
    assert factory._resolve_provider("af/gpt-oss-120b") == "9router"
    assert factory._resolve_provider("combo/free-fallback") == "9router"
    assert factory._resolve_provider("9r/my-custom-model") == "9router"

    # Client instantiation via ProviderRegistry
    client = ProviderRegistry.create_client(
        provider_name="9router",
        model_name="kr/claude-sonnet-4.5",
        settings=mock_settings,
        role_config={"max_tokens": 4096, "temperature": 0.2},
        task_role="test_role"
    )
    assert isinstance(client, NineRouterProvider)
    assert client.provider_name == "9router"
    assert client.model == "kr/claude-sonnet-4.5"
    assert client.max_tokens == 4096
    assert client.temperature == 0.2


@pytest.mark.asyncio
async def test_nine_router_generate_mocked(mock_settings):
    provider = NineRouterProvider(model="kr/claude-sonnet-4.5", settings=mock_settings)

    mock_choice = mock.MagicMock()
    mock_choice.message.content = "Halo dari 9Router AI!"
    mock_choice.message.reasoning = None
    mock_choice.message.model_extra = {}

    mock_resp = mock.MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock.MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)

    with mock.patch.object(provider, "_call_chat_completions_with_recovery", mock.AsyncMock(return_value=mock_resp)):
        result = await provider.generate("Halo!", system="Kamu adalah AI trading.")
        assert result == "Halo dari 9Router AI!"


@pytest.mark.asyncio
async def test_nine_router_classify_json_mocked(mock_settings):
    provider = NineRouterProvider(model="if/kimi-k2", settings=mock_settings)

    mock_choice = mock.MagicMock()
    mock_choice.message.content = '{"signal": "BUY", "confidence": 0.88}'
    mock_choice.message.reasoning = None
    mock_choice.message.model_extra = {}

    mock_resp = mock.MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock.MagicMock(prompt_tokens=15, completion_tokens=25, total_tokens=40)

    schema = {
        "type": "object",
        "properties": {
            "signal": {"type": "string"},
            "confidence": {"type": "number"}
        }
    }

    with mock.patch.object(provider, "_call_chat_completions_with_recovery", mock.AsyncMock(return_value=mock_resp)):
        res = await provider.classify_json("Analisis EURUSD", schema=schema)
        assert isinstance(res, dict)
        assert res.get("signal") == "BUY"
        assert res.get("confidence") == 0.88


@pytest.mark.asyncio
async def test_nine_router_fetch_available_models_mocked(mock_settings):
    provider = NineRouterProvider(model="kr/claude-sonnet-4.5", settings=mock_settings)

    mock_m1 = mock.MagicMock(id="kr/claude-sonnet-4.5", owned_by="kiro")
    mock_m2 = mock.MagicMock(id="if/kimi-k2", owned_by="iflow")
    mock_m3 = mock.MagicMock(id="ag/gemini-3.8-flash-high", owned_by="antigravity")

    mock_models_resp = mock.MagicMock()
    mock_models_resp.data = [mock_m1, mock_m2, mock_m3]

    mock_openai_client = mock.MagicMock()
    mock_openai_client.models.list = mock.AsyncMock(return_value=mock_models_resp)
    provider.client = mock_openai_client

    models = await provider.fetch_available_models()
    assert len(models) == 3
    assert models[0]["id"] == "kr/claude-sonnet-4.5"
    assert models[0]["is_free"] is True
    assert models[1]["id"] == "if/kimi-k2"
    assert models[1]["is_free"] is True
    assert models[2]["id"] == "ag/gemini-3.8-flash-high"
    assert models[2]["is_free"] is False


@pytest.mark.asyncio
async def test_nine_router_fetch_available_models_graceful_failure(mock_settings):
    provider = NineRouterProvider(model="kr/claude-sonnet-4.5", settings=mock_settings)

    mock_openai_client = mock.MagicMock()
    mock_openai_client.models.list = mock.AsyncMock(side_effect=ConnectionRefusedError("9router offline"))
    provider.client = mock_openai_client

    # Harap tidak melempar Exception, melainkan me-return list kosong
    models = await provider.fetch_available_models()
    assert models == []


def test_nine_router_is_alive_and_ensure_running():
    mock_sock = mock.MagicMock()
    with mock.patch("socket.create_connection", return_value=mock_sock):
        assert NineRouterProvider.is_alive("127.0.0.1", 20128) is True
        assert NineRouterProvider.ensure_running("127.0.0.1", 20128) is True

    with mock.patch("socket.create_connection", side_effect=ConnectionRefusedError()):
        assert NineRouterProvider.is_alive("127.0.0.1", 20128) is False

    # Test auto spawn when no binary is found
    with mock.patch("socket.create_connection", side_effect=ConnectionRefusedError()), \
         mock.patch("shutil.which", return_value=None):
        assert NineRouterProvider.ensure_running("127.0.0.1", 20128, wait_seconds=0.1) is False

    # Test auto spawn when 9router binary is found and starts
    with mock.patch("socket.create_connection", side_effect=[ConnectionRefusedError(), mock_sock, mock_sock]), \
         mock.patch("shutil.which", side_effect=lambda cmd: "9router" if cmd == "9router" else None), \
         mock.patch("subprocess.Popen") as mock_popen:
        assert NineRouterProvider.ensure_running("127.0.0.1", 20128, wait_seconds=0.5) is True
        mock_popen.assert_called_once()


def test_llm_factory_create_client_instance_ninerouter_alias(mock_settings):
    """Test LLMFactory._create_client_instance properly links ninerouter provider config with 9router model."""
    factory = LLMFactory(mock_settings)
    client = factory._create_client_instance("kr/claude-sonnet-4.5", {"max_tokens": 1024})
    assert client is not None
    assert client.provider_name == "9router"
    assert client.base_url == "http://localhost:20128/v1"


@pytest.mark.asyncio
async def test_startup_checker_ninerouter_ping_finds_model(mock_settings):
    """Test that StartupChecker._check_api_keys finds model for 'ninerouter' provider without warning."""
    from agent.startup_checks import StartupChecker
    checker = StartupChecker(mock_settings)

    mock_client = mock.MagicMock()
    mock_client.generate = mock.AsyncMock(return_value="pong")
    mock_client.last_served_model = "kr/claude-sonnet-4.5"

    with mock.patch("analysis.providers.nine_router_provider.NineRouterProvider.ensure_running", return_value=True), \
         mock.patch("analysis.providers.llm_factory.LLMFactory._create_client_instance", return_value=mock_client), \
         mock.patch("agent.startup_checks.logger.warning") as mock_warn:
        ok, warns = await checker._check_api_keys()
        assert ok is True
        # Verify no "No model found in catalog for provider 'ninerouter'" warning
        for call_args in mock_warn.call_args_list:
            msg = call_args[0][0]
            assert "No model found in catalog for provider 'ninerouter'" not in msg



