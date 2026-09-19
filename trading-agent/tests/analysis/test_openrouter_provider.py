import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.providers.openrouter_provider import OpenRouterProvider
from analysis.providers.llm_factory import LLMFactory, create_client, get_client_for_task


def test_openrouter_provider_init():
    """Provider harus membaca OPENROUTER_API_KEY dan mengatur base_url serta headers OpenRouter."""
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'sk-or-test-key-123'}, clear=True):
        provider = OpenRouterProvider(model="claude-sonnet-5")
        assert provider.api_key == "sk-or-test-key-123"
        assert provider.client is not None
        assert str(provider.client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
        assert provider.client.default_headers.get("HTTP-Referer") == "https://monika.local"
        assert provider.client.default_headers.get("X-Title") == "Monika MT5 Trading Agent"


def test_openrouter_reasoning_params():
    """Format reasoning effort OpenRouter harus masuk ke extra_body['reasoning']['effort'] secara aman beserta token floor."""
    provider = OpenRouterProvider(model="claude-sonnet-5", api_key="test-key")
    expected_efforts = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "high",
        "max": "high"
    }
    expected_floors = {
        "low": 2048,
        "medium": 4096,
        "high": 8192,
        "xhigh": 16384,
        "max": 32768
    }
    for level, exp_effort in expected_efforts.items():
        provider.thinking_level = level
        kwargs = {"model": provider.model, "messages": []}
        provider._apply_reasoning_params(kwargs)
        assert "extra_body" in kwargs
        assert kwargs["extra_body"]["reasoning"] == {"effort": exp_effort}
        assert kwargs.get("max_tokens") == expected_floors[level]


def test_openrouter_reasoning_none():
    """Jika thinking_level 'none' atau kosong, extra_body reasoning tidak ditambahkan."""
    provider = OpenRouterProvider(model="claude-sonnet-5", api_key="test-key")
    provider.thinking_level = "none"

    kwargs = {"model": provider.model, "messages": []}
    provider._apply_reasoning_params(kwargs)

    assert "reasoning" not in kwargs.get("extra_body", {})


@pytest.mark.asyncio
async def test_openrouter_generate():
    """OpenRouterProvider.generate() memanggil chat.completions.create dengan benar."""
    provider = OpenRouterProvider(model="claude-sonnet-5", api_key="test-key")

    mock_choice = MagicMock()
    mock_choice.message.content = "OpenRouter response"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    with patch.object(provider.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_resp
        res = await provider.generate("Test prompt", system="System prompt", temperature=0.2)

        assert res == "OpenRouter response"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-sonnet-5"
        assert call_kwargs["temperature"] == 0.2
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0] == {"role": "system", "content": "System prompt"}
        assert call_kwargs["messages"][1] == {"role": "user", "content": "Test prompt"}


@pytest.mark.asyncio
async def test_openrouter_classify_json():
    """OpenRouterProvider.classify_json() menghasilkan dict JSON yang valid."""
    provider = OpenRouterProvider(model="gpt-5.6-luna", api_key="test-key")

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"status": "approved", "score": 8.5})
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    with patch.object(provider.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_resp
        schema = {"type": "object", "properties": {"status": {"type": "string"}}}
        res = await provider.classify_json("Analyze this", schema=schema)

        assert isinstance(res, dict)
        assert res["status"] == "approved"
        assert res["score"] == 8.5


@pytest.mark.asyncio
async def test_openrouter_run_agent_402_billing_error():
    """Error 402 / Insufficient credits harus menandai is_billing_error=True."""
    provider = OpenRouterProvider(model="claude-sonnet-5", api_key="test-key")

    with patch.object(provider, 'run_tool_agent', side_effect=Exception("402 Payment Required: Insufficient credits")):
        session = MagicMock()
        res = await provider.run_agent(session, "sys", "user", tools=[], stage_name="stage1_test")

        assert res["success"] is False
        assert res.get("is_billing_error") is True


@pytest.mark.asyncio
async def test_openrouter_token_logging():
    """Token usage logging harus mencatat provider sebagai 'openrouter'."""
    provider = OpenRouterProvider(model="claude-sonnet-5", api_key="test-key")

    mock_session = AsyncMock()
    with patch('database.models.TokenUsageLog') as mock_log_cls:
        await provider._save_token_usage(
            model_name="claude-sonnet-5",
            task_name="test_task",
            input_tokens=100,
            output_tokens=50,
            session=mock_session
        )
        mock_log_cls.assert_called_once()
        kw = mock_log_cls.call_args.kwargs
        assert kw["provider"] == "openrouter"
        assert kw["model_name"] == "claude-sonnet-5"
        assert kw["task_name"] == "test_task"
        assert kw["input_tokens"] == 100
        assert kw["output_tokens"] == 50
        assert kw["total_tokens"] == 150
        mock_session.add.assert_called_once()


def test_factory_creates_openrouter_client():
    """LLMFactory harus mendeteksi dan membuat OpenRouterProvider untuk model OpenRouter."""
    settings = {
        "llm": {
            "providers": {
                "openrouter": {"enabled": True}
            },
            "model_catalog": {
                "claude-sonnet-5": {"provider": "openrouter"}
            },
            "task_roles": {
                "paid_task": {
                    "primary": "claude-sonnet-5",
                    "max_tokens": 4096,
                    "temperature": 0.1,
                    "thinking": {"openrouter": "high"}
                }
            }
        }
    }
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        factory = LLMFactory(settings)
        assert factory._resolve_provider("claude-sonnet-5") == "openrouter"

        client = factory._create_client_instance("claude-sonnet-5", settings["llm"]["task_roles"]["paid_task"])
        assert isinstance(client, OpenRouterProvider)
        assert client.model == "anthropic/claude-sonnet-5"
        assert client.raw_model_name == "claude-sonnet-5"
        assert client.max_tokens == 4096
        assert client.default_temperature == 0.1
        assert client.thinking_level == "high"


def test_openrouter_ox_alpha_resolution_and_init():
    """Test spesifik inisialisasi model ox-alpha ke stealth/ox-alpha."""
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        provider = OpenRouterProvider(model="ox-alpha", max_tokens=16384)
        assert provider.model == "stealth/ox-alpha"
        assert provider.raw_model_name == "ox-alpha"
        assert provider.max_tokens == 16384

        provider_direct = OpenRouterProvider(model="stealth/ox-alpha")
        assert provider_direct.model == "stealth/ox-alpha"


def test_openrouter_model_aliases_1to1_accuracy():
    """Seluruh model alias di OPENROUTER_MODEL_ALIASES harus memetakan ke vendor model slug yang tepat."""
    expected_mappings = {
        "claude-sonnet-5": "anthropic/claude-sonnet-5",
        "claude-opus-5": "anthropic/claude-opus-5",
        "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
        "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5-20251001",
        "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
        "gpt-5.6-sol": "openai/gpt-5.6-sol",
        "gpt-5.6-terra": "openai/gpt-5.6-terra",
        "gpt-5.6-luna": "openai/gpt-5.6-luna",
        "gemini-3.7-flash": "google/gemini-3.7-flash",
        "gemini-3.5-flash-lite": "google/gemini-3.5-flash-lite",
        "ox-alpha": "stealth/ox-alpha",
        "glm-5.2": "z-ai/glm-5.2",
        "glm-5.2:free": "z-ai/glm-5.2:free",
        "gemma-4-31b:free": "google/gemma-4-31b-it:free",
        "gemma-4-26b:free": "google/gemma-4-26b-a4b-it:free",
        "nemotron-3-ultra:free": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nemotron-3.5-lightning:free": "nvidia/nemotron-3.5-lightning:free",
        "nemotron-3-super:free": "nvidia/nemotron-3-super-120b-a12b:free",
        "nemotron-3-nano:free": "nvidia/nemotron-3-nano-30b-a3b:free",
        "nemotron-3-nano-omni:free": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "nemotron-nano-12b-vl:free": "nvidia/nemotron-nano-12b-v2-vl:free",
        "nemotron-nano-9b:free": "nvidia/nemotron-nano-9b-v2:free",
        "nemotron-3.5-safety:free": "nvidia/nemotron-3.5-content-safety:free",
        "north-mini-code:free": "cohere/north-mini-code:free",
        "laguna-s-2.1:free": "poolside/laguna-s-2.1:free",
        "laguna-xs-2.1:free": "poolside/laguna-xs-2.1:free",
        "inkling:free": "thinkingmachines/inkling:free",
        "inkling-small:free": "thinkingmachines/inkling-small:free",
        "dots-3-note:free": "dots-studio/dots-3-note-preview:free",
        "lfm-2.5-2.6b:free": "liquid/lfm-2.5-2.6b:free",
        "openrouter/free": "openrouter/free",
        "openrouter-free": "openrouter/free",
    }
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        for alias, target in expected_mappings.items():
            p = OpenRouterProvider(model=alias)
            assert p.model == target, f"Alias '{alias}' expected to resolve to '{target}', got '{p.model}'"


def test_openrouter_glm_5_2_free_resolution_and_init():
    """Test spesifik inisialisasi model glm-5.2:free ke z-ai/glm-5.2:free."""
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        provider = OpenRouterProvider(model="glm-5.2:free", max_tokens=16384)
        assert provider.model == "z-ai/glm-5.2:free"
        assert provider.raw_model_name == "glm-5.2:free"
        assert provider.max_tokens == 16384

        provider_direct = OpenRouterProvider(model="z-ai/glm-5.2:free")
        assert provider_direct.model == "z-ai/glm-5.2:free"


def test_openrouter_all_free_tier_models_resolution():
    """Memastikan semua 18 model free tier baru OpenRouter dapat diinisialisasi dan di-resolve dengan benar."""
    free_tier_models = [
        ("google/gemma-4-31b-it:free", "google/gemma-4-31b-it:free"),
        ("gemma-4-31b:free", "google/gemma-4-31b-it:free"),
        ("google/gemma-4-26b-a4b-it:free", "google/gemma-4-26b-a4b-it:free"),
        ("gemma-4-26b:free", "google/gemma-4-26b-a4b-it:free"),
        ("nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("nemotron-3-ultra:free", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("nvidia/nemotron-3.5-lightning:free", "nvidia/nemotron-3.5-lightning:free"),
        ("nemotron-3.5-lightning:free", "nvidia/nemotron-3.5-lightning:free"),
        ("nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nemotron-3-super:free", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia/nemotron-3-nano-30b-a3b:free", "nvidia/nemotron-3-nano-30b-a3b:free"),
        ("nemotron-3-nano:free", "nvidia/nemotron-3-nano-30b-a3b:free"),
        ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
        ("nemotron-3-nano-omni:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
        ("nvidia/nemotron-nano-12b-v2-vl:free", "nvidia/nemotron-nano-12b-v2-vl:free"),
        ("nemotron-nano-12b-vl:free", "nvidia/nemotron-nano-12b-v2-vl:free"),
        ("nvidia/nemotron-nano-9b-v2:free", "nvidia/nemotron-nano-9b-v2:free"),
        ("nemotron-nano-9b:free", "nvidia/nemotron-nano-9b-v2:free"),
        ("nvidia/nemotron-3.5-content-safety:free", "nvidia/nemotron-3.5-content-safety:free"),
        ("nemotron-3.5-safety:free", "nvidia/nemotron-3.5-content-safety:free"),
        ("cohere/north-mini-code:free", "cohere/north-mini-code:free"),
        ("north-mini-code:free", "cohere/north-mini-code:free"),
        ("poolside/laguna-s-2.1:free", "poolside/laguna-s-2.1:free"),
        ("laguna-s-2.1:free", "poolside/laguna-s-2.1:free"),
        ("poolside/laguna-xs-2.1:free", "poolside/laguna-xs-2.1:free"),
        ("laguna-xs-2.1:free", "poolside/laguna-xs-2.1:free"),
        ("thinkingmachines/inkling:free", "thinkingmachines/inkling:free"),
        ("inkling:free", "thinkingmachines/inkling:free"),
        ("thinkingmachines/inkling-small:free", "thinkingmachines/inkling-small:free"),
        ("inkling-small:free", "thinkingmachines/inkling-small:free"),
        ("dots-studio/dots-3-note-preview:free", "dots-studio/dots-3-note-preview:free"),
        ("dots-3-note:free", "dots-studio/dots-3-note-preview:free"),
        ("liquid/lfm-2.5-2.6b:free", "liquid/lfm-2.5-2.6b:free"),
        ("lfm-2.5-2.6b:free", "liquid/lfm-2.5-2.6b:free"),
        ("openrouter/free", "openrouter/free"),
        ("openrouter-free", "openrouter/free"),
    ]
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        for raw_name, target in free_tier_models:
            provider = OpenRouterProvider(model=raw_name)
            assert provider.model == target, f"Model '{raw_name}' expected to resolve to '{target}', got '{provider.model}'"
            assert provider.raw_model_name == raw_name


def test_openrouter_free_model_rotates_across_all_keys():
    """Model gratis (misal ox-alpha atau :free) harus memutar seluruh kunci (paid + free keys)."""
    env = {
        'OPENROUTER_PAID_API_KEY': 'sk-or-paid-1',
        'OPENROUTER_API_KEYS': 'sk-or-free-1, sk-or-free-2',
    }
    with patch.dict('os.environ', env, clear=True):
        provider = OpenRouterProvider(model="ox-alpha")
        assert provider.is_free is True
        assert len(provider._all_keys) == 3
        assert "sk-or-paid-1" in provider._all_keys
        assert "sk-or-free-1" in provider._all_keys
        assert "sk-or-free-2" in provider._all_keys

        # Test rotation across keys
        keys_obtained = set()
        for _ in range(6):
            k = provider._get_api_key()
            if k:
                keys_obtained.add(k)
        assert keys_obtained == {"sk-or-paid-1", "sk-or-free-1", "sk-or-free-2"}


def test_openrouter_paid_model_uses_paid_key_only():
    """Model berbayar (misal claude-sonnet-5) HANYA boleh menggunakan paid key."""
    env = {
        'OPENROUTER_PAID_API_KEY': 'sk-or-paid-1',
        'OPENROUTER_API_KEYS': 'sk-or-free-1, sk-or-free-2',
    }
    with patch.dict('os.environ', env, clear=True):
        provider = OpenRouterProvider(model="claude-sonnet-5")
        assert provider.is_free is False
        assert provider._paid_key == "sk-or-paid-1"

        # Always returns paid key
        for _ in range(5):
            k = provider._get_api_key()
            assert k == "sk-or-paid-1"


def test_openrouter_key_cooldown_on_429():
    """Saat key terkena 429 pada model tertentu, cooldown aktif untuk model tersebut."""
    import time
    env = {
        'OPENROUTER_PAID_API_KEY': 'sk-or-paid-1',
        'OPENROUTER_API_KEYS': 'sk-or-free-1, sk-or-free-2',
    }
    with patch.dict('os.environ', env, clear=True):
        # Reset cooldowns
        OpenRouterProvider.reset_cooldowns()
        provider = OpenRouterProvider(model="ox-alpha")

        # Pasang cooldown pada sk-or-paid-1 dan sk-or-free-1 khusus ox-alpha / stealth/ox-alpha
        OpenRouterProvider._model_key_cooldowns[('sk-or-paid-1', 'stealth/ox-alpha')] = time.time() + 60
        OpenRouterProvider._model_key_cooldowns[('sk-or-free-1', 'stealth/ox-alpha')] = time.time() + 60

        # Harus menghasilkan sk-or-free-2 untuk ox-alpha
        assert provider._get_api_key() == 'sk-or-free-2'
        OpenRouterProvider.reset_cooldowns()


def test_openrouter_per_model_cooldown_isolation():
    """
    Memverifikasi isolasi cooldown per-model:
    Jika ox-alpha mengalami rate limit / upstream congestion pada suatu key,
    key tersebut HARUS TETAP DAPAT DIGUNAKAN untuk model lain (misal GLM 5.2 free).
    """
    import time
    env = {
        'OPENROUTER_PAID_API_KEY': 'sk-or-paid-1',
        'OPENROUTER_API_KEYS': 'sk-or-free-1, sk-or-free-2',
    }
    with patch.dict('os.environ', env, clear=True):
        OpenRouterProvider.reset_cooldowns()

        provider_ox = OpenRouterProvider(model="ox-alpha")
        provider_glm = OpenRouterProvider(model="glm-5.2:free")

        # Simulasikan upstream congestion pada ox-alpha untuk sk-or-free-1 dan sk-or-free-2
        err_upstream = Exception("Error code: 429 - stealth/ox-alpha is temporarily rate-limited upstream.")
        OpenRouterProvider._handle_rate_limit_error("sk-or-free-1", err_upstream, "generate_content", "stealth/ox-alpha")
        OpenRouterProvider._handle_rate_limit_error("sk-or-free-2", err_upstream, "generate_content", "stealth/ox-alpha")
        OpenRouterProvider._handle_rate_limit_error("sk-or-paid-1", err_upstream, "generate_content", "stealth/ox-alpha")

        # Semua key sekarang in cooldown untuk ox-alpha
        assert provider_ox._get_api_key() is None

        # NAMUN untuk GLM 5.2 free, key-key tersebut HARUS tetap bisa digunakan!
        glm_key = provider_glm._get_api_key()
        assert glm_key in {"sk-or-paid-1", "sk-or-free-1", "sk-or-free-2"}

        # Verifikasi status cooldown mencatat per-model
        status = OpenRouterProvider.get_cooldown_status()
        assert any("stealth/ox-alpha" in k for k in status.keys())
        assert not any("z-ai/glm-5.2:free" in k for k in status.keys())

        OpenRouterProvider.reset_cooldowns()


@pytest.mark.asyncio
async def test_openrouter_rate_limiter_module():
    """Memverifikasi OpenRouterRateLimiter try_acquire dan get_usage."""
    from utils.api.openrouter_rate_limiter import OpenRouterRateLimiter, is_free_tier_model
    assert is_free_tier_model("ox-alpha") is True
    assert is_free_tier_model("google/gemma-4-31b-it:free") is True
    assert is_free_tier_model("claude-sonnet-5") is False

    limiter = OpenRouterRateLimiter()
    acquired = await limiter.try_acquire("ox-alpha")
    assert acquired is True

    usage = await limiter.get_usage("ox-alpha")
    assert usage["used"] >= 1
    assert usage["is_free_tier"] is True


def test_openrouter_handle_rate_limit_classification():
    """Memverifikasi presisi klasifikasi rate limit OpenRouter (Generic 429 vs Retry hint vs Upstream vs RPD)."""
    import time
    from utils.api.openrouter_rate_limiter import OpenRouterRateLimiter
    OpenRouterProvider.reset_cooldowns()

    # 1. Generic 429 ('Rate limit exceeded') pada model tertentu -> harus cooldown 65s (bukan 24h)
    err_generic = Exception("Error code: 429 - {'error': {'message': 'Rate limit exceeded', 'code': 429}}")
    rot1 = OpenRouterProvider._handle_rate_limit_error("test-key-1", err_generic, "generate_content", "stealth/ox-alpha")
    assert rot1 is True
    cd1 = OpenRouterProvider._model_key_cooldowns.get(("test-key-1", "stealth/ox-alpha"), 0) - time.time()
    assert 60.0 <= cd1 <= 66.0, f"Expected ~65s cooldown, got {cd1}"

    # 2. 429 with retry hint ('try again in 12.5s') -> cooldown ~17.5s
    err_retry = Exception("429 Too Many Requests: please try again in 12.5s")
    rot2 = OpenRouterProvider._handle_rate_limit_error("test-key-2", err_retry, "generate", "z-ai/glm-5.2:free")
    assert rot2 is True
    cd2 = OpenRouterProvider._model_key_cooldowns.get(("test-key-2", "z-ai/glm-5.2:free"), 0) - time.time()
    assert 16.0 <= cd2 <= 19.0, f"Expected ~17.5s cooldown, got {cd2}"

    # 3. Upstream provider shared pool congestion -> cooldown 60s & fail-fast (should_rotate=False)
    err_upstream = Exception("Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'stealth/ox-alpha is temporarily rate-limited upstream. Please retry shortly.', 'limit_source': 'upstream_provider_shared_pool'}}}")
    rot_up = OpenRouterProvider._handle_rate_limit_error("test-key-upstream", err_upstream, "generate", "stealth/ox-alpha")
    assert rot_up is False
    cd_up = OpenRouterProvider._model_key_cooldowns.get(("test-key-upstream", "stealth/ox-alpha"), 0) - time.time()
    assert 55.0 <= cd_up <= 65.0, f"Expected ~60s cooldown, got {cd_up}"

    # 4. Explicit RPD ('Free tier daily limit reached') -> cooldown 24h (86400s)
    err_rpd = Exception("Error code: 429 - {'error': {'message': 'Free tier daily limit reached for model', 'code': 429}}")
    rot3 = OpenRouterProvider._handle_rate_limit_error("test-key-3", err_rpd, "generate_content", "stealth/ox-alpha")
    assert rot3 is True
    cd3 = OpenRouterProvider._model_key_cooldowns.get(("test-key-3", "stealth/ox-alpha"), 0) - time.time()
    assert 86390.0 <= cd3 <= 86405.0, f"Expected ~86400s cooldown, got {cd3}"

    # 5. Global fallback when model is omitted
    rot_glob = OpenRouterProvider._handle_rate_limit_error("test-key-global", err_generic, "generate")
    assert rot_glob is True
    cd_glob = OpenRouterProvider._key_cooldowns.get("test-key-global", 0) - time.time()
    assert 60.0 <= cd_glob <= 66.0

    # 6. Test reset_cooldowns targeted & bulk
    # Reset single key & model
    freed = OpenRouterProvider.reset_cooldowns("test-key-1", "stealth/ox-alpha")
    assert freed == 1
    assert ("test-key-1", "stealth/ox-alpha") not in OpenRouterProvider._model_key_cooldowns

    # Reset by model only
    freed_m = OpenRouterProvider.reset_cooldowns(model="z-ai/glm-5.2:free")
    assert freed_m >= 1

    # Reset all
    all_freed = OpenRouterProvider.reset_cooldowns()
    assert all_freed >= 1
    assert len(OpenRouterProvider._model_key_cooldowns) == 0
    assert len(OpenRouterProvider._key_cooldowns) == 0

    # 7. Test OpenRouterRateLimiter.reset
    OpenRouterRateLimiter._daily_counts["test-model"] = {"date": "2026-08-25", "count": 50}
    OpenRouterRateLimiter.reset("test-model")
    assert "test-model" not in OpenRouterRateLimiter._daily_counts

    OpenRouterRateLimiter._daily_counts["all-model"] = {"date": "2026-08-25", "count": 100}
    OpenRouterRateLimiter.reset()
    assert len(OpenRouterRateLimiter._daily_counts) == 0


def test_openrouter_logger_name():
    """Memverifikasi namespace logger adalah TradingAgent.OpenRouterProvider."""
    from analysis.providers.openrouter_provider import logger
    assert logger.name == "TradingAgent.OpenRouterProvider"


@pytest.mark.asyncio
async def test_openrouter_upstream_fail_fast_no_key_rotation():
    """
    Memverifikasi bahwa ketika terjadi error Upstream Provider Congested / Shared Pool,
    provider langsung Fail-Fast (hanya 1 API call, TIDAK merotasi ke sisa kunci lain).
    """
    env = {
        'OPENROUTER_API_KEYS': 'sk-or-free-1, sk-or-free-2, sk-or-free-3, sk-or-free-4',
    }
    with patch.dict('os.environ', env, clear=True):
        OpenRouterProvider.reset_cooldowns()
        provider = OpenRouterProvider(model="z-ai/glm-5.2:free")

        # Mock chat.completions.create untuk selalu melempar upstream 429
        mock_create = AsyncMock()
        err_upstream = Exception("Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'z-ai/glm-5.2:free is temporarily rate-limited upstream.', 'limit_source': 'upstream_provider_shared_pool'}}}")
        mock_create.side_effect = err_upstream

        with patch.object(provider, '_get_client_for_key') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            result = await provider.generate("Test prompt")
            assert result is None
            # HARUS hanya 1 pemanggilan (Fail-Fast), tidak merotasi ke 4 key!
            assert mock_create.call_count == 1

            # Pastikan seluruh 4 key sekarang mendapatkan cooldown untuk model ini
            for k in ['sk-or-free-1', 'sk-or-free-2', 'sk-or-free-3', 'sk-or-free-4']:
                assert (k, 'z-ai/glm-5.2:free') in OpenRouterProvider._model_key_cooldowns

        OpenRouterProvider.reset_cooldowns()


@pytest.mark.asyncio
async def test_openrouter_502_503_service_unavailable_fail_fast():
    """
    Memverifikasi bahwa HTTP 502/503 Service Unavailable diperlakukan sebagai model unavailable dan langsung fail-fast.
    """
    env = {
        'OPENROUTER_API_KEYS': 'sk-or-free-1, sk-or-free-2, sk-or-free-3',
    }
    with patch.dict('os.environ', env, clear=True):
        OpenRouterProvider.reset_cooldowns()
        provider = OpenRouterProvider(model="z-ai/glm-5.2:free")

        mock_create = AsyncMock()
        err_503 = Exception("Error code: 503 - {'error': {'message': 'Service Unavailable: No available model provider meets your routing requirements', 'code': 503}}")
        mock_create.side_effect = err_503

        with patch.object(provider, '_get_client_for_key') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            result = await provider.generate_content("sys", "user", response_schema={"type": "object"})
            assert result in ("", None)
            assert mock_create.call_count == 1

        OpenRouterProvider.reset_cooldowns()




